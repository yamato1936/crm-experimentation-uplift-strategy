-- ============================================================
-- Hillstrom Experiment Population
-- Google BigQuery Standard SQL (GoogleSQL)
-- ============================================================
--
-- Purpose:
--   Define the canonical experimental population used by all
--   downstream A/B test and heterogeneous-treatment-effect analyses.
--
-- Design principles:
--   - Preserve all raw experimental units unless an explicit
--     eligibility rule excludes them.
--   - Do not infer or invent a customer identifier.
--   - Preserve treatment assignment exactly as observed.
--   - Separate pre-treatment covariates from post-treatment outcomes.
--   - Use metric-specific outcome eligibility flags.
--   - Do not estimate treatment effects in this file.
--
-- Upstream validation:
--   - Raw rows: 64,000
--   - No missing values
--   - No invalid treatment values
--   - No invalid binary values
--   - No logical outcome inconsistencies
--   - No material SRM or pre-treatment covariate imbalance detected
--
-- Source:
--   `ceus.hillstrom_raw`
--
-- Output:
--   `ceus.experiment_population`
-- ============================================================


-- ============================================================
-- 0. Build canonical experiment population
-- ============================================================

CREATE OR REPLACE TABLE `ceus.experiment_population` AS

WITH typed_source AS (
    SELECT
        -- ----------------------------------------------------
        -- Treatment assignment
        -- ----------------------------------------------------
        CAST(segment AS STRING) AS segment,

        CASE
            WHEN segment = 'No E-Mail' THEN 'control'
            WHEN segment = 'Mens E-Mail' THEN 'mens_email'
            WHEN segment = 'Womens E-Mail' THEN 'womens_email'
            ELSE NULL
        END AS treatment_group,

        -- ----------------------------------------------------
        -- Pre-treatment covariates
        -- ----------------------------------------------------
        SAFE_CAST(recency AS INT64) AS recency,
        SAFE_CAST(history AS FLOAT64) AS history,
        CAST(history_segment AS STRING) AS history_segment,

        SAFE_CAST(mens AS INT64) AS mens,
        SAFE_CAST(womens AS INT64) AS womens,

        CAST(zip_code AS STRING) AS zip_code,
        SAFE_CAST(newbie AS INT64) AS newbie,
        CAST(channel AS STRING) AS channel,

        -- ----------------------------------------------------
        -- Post-treatment outcomes
        -- ----------------------------------------------------
        SAFE_CAST(visit AS INT64) AS visit,
        SAFE_CAST(conversion AS INT64) AS conversion,
        SAFE_CAST(spend AS FLOAT64) AS spend

    FROM `ceus.hillstrom_raw`
),

population_with_flags AS (
    SELECT
        *,

        -- ----------------------------------------------------
        -- Treatment eligibility
        -- ----------------------------------------------------
        treatment_group IS NOT NULL
            AS treatment_eligible,

        -- ----------------------------------------------------
        -- Pre-treatment covariate completeness
        --
        -- This flag defines whether the row can be used in
        -- covariate-adjusted / heterogeneous-effect analyses.
        -- It does NOT depend on post-treatment outcomes.
        -- ----------------------------------------------------
        (
            recency IS NOT NULL
            AND history IS NOT NULL
            AND history_segment IS NOT NULL
            AND mens IN (0, 1)
            AND womens IN (0, 1)
            AND zip_code IS NOT NULL
            AND newbie IN (0, 1)
            AND channel IS NOT NULL
        ) AS pretreatment_eligible,

        -- ----------------------------------------------------
        -- Outcome-specific eligibility
        --
        -- Keep these separate rather than globally dropping
        -- observations because each estimand may use a different
        -- outcome.
        -- ----------------------------------------------------
        visit IN (0, 1)
            AS visit_eligible,

        conversion IN (0, 1)
            AS conversion_eligible,

        (
            spend IS NOT NULL
            AND spend >= 0
        ) AS spend_eligible,

        -- ----------------------------------------------------
        -- Outcome consistency
        --
        -- These checks mirror the upstream data audit and are
        -- retained here as a defensive downstream guardrail.
        -- ----------------------------------------------------
        (
            NOT (
                conversion = 1
                AND spend <= 0
            )
            AND NOT (
                conversion = 0
                AND spend > 0
            )
            AND NOT (
                conversion = 1
                AND visit = 0
            )
            AND spend >= 0
        ) AS outcome_consistent

    FROM typed_source
)

SELECT
    -- Treatment
    segment,
    treatment_group,

    -- Pre-treatment covariates
    recency,
    history,
    history_segment,
    mens,
    womens,
    zip_code,
    newbie,
    channel,

    -- Post-treatment outcomes
    visit,
    conversion,
    spend,

    -- Eligibility flags
    treatment_eligible,
    pretreatment_eligible,
    visit_eligible,
    conversion_eligible,
    spend_eligible,
    outcome_consistent,

    -- --------------------------------------------------------
    -- Canonical experiment eligibility
    --
    -- This does not require any particular outcome to exist.
    -- Outcome eligibility remains metric-specific.
    -- --------------------------------------------------------
    (
        treatment_eligible
        AND pretreatment_eligible
    ) AS experiment_eligible

FROM population_with_flags;


-- ============================================================
-- 1. Population size validation
-- ============================================================

SELECT
    COUNT(*) AS total_rows,

    COUNTIF(experiment_eligible)
        AS experiment_eligible_rows,

    COUNTIF(NOT experiment_eligible)
        AS experiment_ineligible_rows,

    ROUND(
        100 * SAFE_DIVIDE(
            COUNTIF(experiment_eligible),
            COUNT(*)
        ),
        4
    ) AS experiment_eligible_pct

FROM `ceus.experiment_population`;


-- ============================================================
-- 2. Treatment population validation
-- ============================================================

SELECT
    treatment_group,
    segment,

    COUNT(*) AS row_count,

    COUNTIF(experiment_eligible)
        AS experiment_eligible_rows,

    ROUND(
        100 * SAFE_DIVIDE(
            COUNT(*),
            SUM(COUNT(*)) OVER ()
        ),
        4
    ) AS share_of_population_pct

FROM `ceus.experiment_population`

GROUP BY
    treatment_group,
    segment

ORDER BY
    CASE treatment_group
        WHEN 'control' THEN 1
        WHEN 'mens_email' THEN 2
        WHEN 'womens_email' THEN 3
        ELSE 4
    END;


-- ============================================================
-- 3. Eligibility validation
-- ============================================================

SELECT
    COUNTIF(NOT treatment_eligible)
        AS invalid_treatment_rows,

    COUNTIF(NOT pretreatment_eligible)
        AS pretreatment_ineligible_rows,

    COUNTIF(NOT visit_eligible)
        AS visit_ineligible_rows,

    COUNTIF(NOT conversion_eligible)
        AS conversion_ineligible_rows,

    COUNTIF(NOT spend_eligible)
        AS spend_ineligible_rows,

    COUNTIF(NOT outcome_consistent)
        AS outcome_inconsistent_rows

FROM `ceus.experiment_population`;


-- ============================================================
-- 4. Treatment x outcome eligibility
-- ============================================================

SELECT
    treatment_group,

    COUNT(*) AS row_count,

    COUNTIF(visit_eligible)
        AS visit_eligible_rows,

    COUNTIF(conversion_eligible)
        AS conversion_eligible_rows,

    COUNTIF(spend_eligible)
        AS spend_eligible_rows,

    COUNTIF(outcome_consistent)
        AS outcome_consistent_rows

FROM `ceus.experiment_population`

GROUP BY treatment_group

ORDER BY
    CASE treatment_group
        WHEN 'control' THEN 1
        WHEN 'mens_email' THEN 2
        WHEN 'womens_email' THEN 3
        ELSE 4
    END;


-- ============================================================
-- 5. Defensive domain validation
-- ============================================================

SELECT
    COUNTIF(
        treatment_group NOT IN (
            'control',
            'mens_email',
            'womens_email'
        )
        OR treatment_group IS NULL
    ) AS invalid_treatment_group_rows,

    COUNTIF(mens NOT IN (0, 1) OR mens IS NULL)
        AS invalid_mens_rows,

    COUNTIF(womens NOT IN (0, 1) OR womens IS NULL)
        AS invalid_womens_rows,

    COUNTIF(newbie NOT IN (0, 1) OR newbie IS NULL)
        AS invalid_newbie_rows,

    COUNTIF(visit NOT IN (0, 1) OR visit IS NULL)
        AS invalid_visit_rows,

    COUNTIF(conversion NOT IN (0, 1) OR conversion IS NULL)
        AS invalid_conversion_rows,

    COUNTIF(spend < 0 OR spend IS NULL)
        AS invalid_spend_rows

FROM `ceus.experiment_population`;


-- ============================================================
-- 6. Final population summary
-- ============================================================

SELECT
    COUNT(*) AS total_population,

    COUNTIF(treatment_group = 'control')
        AS control_n,

    COUNTIF(treatment_group = 'mens_email')
        AS mens_email_n,

    COUNTIF(treatment_group = 'womens_email')
        AS womens_email_n,

    COUNTIF(experiment_eligible)
        AS experiment_eligible_n,

    COUNTIF(
        experiment_eligible
        AND conversion_eligible
        AND outcome_consistent
    ) AS conversion_analysis_n,

    COUNTIF(
        experiment_eligible
        AND visit_eligible
        AND outcome_consistent
    ) AS visit_analysis_n,

    COUNTIF(
        experiment_eligible
        AND spend_eligible
        AND outcome_consistent
    ) AS spend_analysis_n

FROM `ceus.experiment_population`;


-- ============================================================
-- Variable roles
-- ============================================================
--
-- Treatment:
--   segment
--   treatment_group
--
-- Pre-treatment covariates:
--   recency
--   history
--   history_segment
--   mens
--   womens
--   zip_code
--   newbie
--   channel
--
-- Post-treatment outcomes:
--   visit
--   conversion
--   spend
--
-- Important:
--   No customer ID exists in the source dataset.
--   No synthetic customer identifier is introduced here.
--
--   Identical observed rows are retained because identical observed
--   covariates/outcomes do not establish that two rows represent the
--   same experimental unit.
--
--   All downstream experiment analyses should use
--   `ceus.experiment_population` rather than querying
--   `ceus.hillstrom_raw` directly.
--
-- ============================================================