-- ============================================================
-- Hillstrom Segment Analysis
-- Google BigQuery Standard SQL (GoogleSQL)
-- ============================================================
--
-- Purpose:
--   Construct descriptive treatment-arm metrics across
--   pre-treatment customer segments.
--
-- This file supports heterogeneous treatment effect analysis.
--
-- Upstream:
--   `ceus.experiment_population`
--
-- Outputs:
--   `ceus.segment_metrics`
--   `ceus.segment_lifts`
--
-- Segment variables:
--   recency
--   history_segment
--   mens
--   womens
--   newbie
--   channel
--   zip_code
--
-- IMPORTANT:
--   Only pre-treatment variables are used for segmentation.
--
--   Do NOT segment on:
--     visit
--     conversion
--     spend
--
--   These are post-treatment outcomes.
--
-- Statistical inference belongs in:
--   src/heterogeneity.py
--
-- This SQL does NOT calculate:
--   - p-values
--   - confidence intervals
--   - interaction tests
--   - multiple-testing corrections
--   - CATE model estimates
-- ============================================================


-- ============================================================
-- 0. Build long-form Treatment x Segment metrics
-- ============================================================

CREATE OR REPLACE TABLE `ceus.segment_metrics` AS

WITH eligible_population AS (

    SELECT
        treatment_group,

        -- Pre-treatment covariates
        recency,
        history_segment,
        mens,
        womens,
        newbie,
        channel,
        zip_code,

        -- Post-treatment outcomes
        visit,
        conversion,
        spend,

        -- Metric-specific eligibility
        visit_eligible,
        conversion_eligible,
        spend_eligible,
        outcome_consistent

    FROM `ceus.experiment_population`

    WHERE experiment_eligible
),

segment_membership AS (

    -- --------------------------------------------------------
    -- Recency
    -- --------------------------------------------------------

    SELECT
        treatment_group,
        'recency' AS segment_variable,
        CAST(recency AS STRING) AS segment_value,

        visit,
        conversion,
        spend,

        visit_eligible,
        conversion_eligible,
        spend_eligible,
        outcome_consistent

    FROM eligible_population

    WHERE recency IS NOT NULL


    UNION ALL


    -- --------------------------------------------------------
    -- Historical customer value band
    -- --------------------------------------------------------

    SELECT
        treatment_group,
        'history_segment' AS segment_variable,
        history_segment AS segment_value,

        visit,
        conversion,
        spend,

        visit_eligible,
        conversion_eligible,
        spend_eligible,
        outcome_consistent

    FROM eligible_population

    WHERE history_segment IS NOT NULL


    UNION ALL


    -- --------------------------------------------------------
    -- Previously purchased men's merchandise
    -- --------------------------------------------------------

    SELECT
        treatment_group,
        'mens' AS segment_variable,
        CAST(mens AS STRING) AS segment_value,

        visit,
        conversion,
        spend,

        visit_eligible,
        conversion_eligible,
        spend_eligible,
        outcome_consistent

    FROM eligible_population

    WHERE mens IS NOT NULL


    UNION ALL


    -- --------------------------------------------------------
    -- Previously purchased women's merchandise
    -- --------------------------------------------------------

    SELECT
        treatment_group,
        'womens' AS segment_variable,
        CAST(womens AS STRING) AS segment_value,

        visit,
        conversion,
        spend,

        visit_eligible,
        conversion_eligible,
        spend_eligible,
        outcome_consistent

    FROM eligible_population

    WHERE womens IS NOT NULL


    UNION ALL


    -- --------------------------------------------------------
    -- New customer status
    -- --------------------------------------------------------

    SELECT
        treatment_group,
        'newbie' AS segment_variable,
        CAST(newbie AS STRING) AS segment_value,

        visit,
        conversion,
        spend,

        visit_eligible,
        conversion_eligible,
        spend_eligible,
        outcome_consistent

    FROM eligible_population

    WHERE newbie IS NOT NULL


    UNION ALL


    -- --------------------------------------------------------
    -- Historical purchase channel
    -- --------------------------------------------------------

    SELECT
        treatment_group,
        'channel' AS segment_variable,
        channel AS segment_value,

        visit,
        conversion,
        spend,

        visit_eligible,
        conversion_eligible,
        spend_eligible,
        outcome_consistent

    FROM eligible_population

    WHERE channel IS NOT NULL


    UNION ALL


    -- --------------------------------------------------------
    -- Geographic classification
    -- --------------------------------------------------------

    SELECT
        treatment_group,
        'zip_code' AS segment_variable,
        zip_code AS segment_value,

        visit,
        conversion,
        spend,

        visit_eligible,
        conversion_eligible,
        spend_eligible,
        outcome_consistent

    FROM eligible_population

    WHERE zip_code IS NOT NULL
),

aggregated AS (

    SELECT
        segment_variable,
        segment_value,
        treatment_group,

        -- ----------------------------------------------------
        -- Segment population
        -- ----------------------------------------------------
        COUNT(*) AS segment_n,


        -- ----------------------------------------------------
        -- Visit
        -- ----------------------------------------------------
        COUNTIF(
            visit_eligible
            AND outcome_consistent
        ) AS visit_n,

        COUNTIF(
            visit_eligible
            AND outcome_consistent
            AND visit = 1
        ) AS visit_count,

        AVG(
            IF(
                visit_eligible
                AND outcome_consistent,
                CAST(visit AS FLOAT64),
                NULL
            )
        ) AS visit_rate,


        -- ----------------------------------------------------
        -- Conversion
        -- ----------------------------------------------------
        COUNTIF(
            conversion_eligible
            AND outcome_consistent
        ) AS conversion_n,

        COUNTIF(
            conversion_eligible
            AND outcome_consistent
            AND conversion = 1
        ) AS conversion_count,

        AVG(
            IF(
                conversion_eligible
                AND outcome_consistent,
                CAST(conversion AS FLOAT64),
                NULL
            )
        ) AS conversion_rate,


        -- ----------------------------------------------------
        -- Spend
        --
        -- Includes zero-spend randomized users.
        -- ----------------------------------------------------
        COUNTIF(
            spend_eligible
            AND outcome_consistent
        ) AS spend_n,

        SUM(
            IF(
                spend_eligible
                AND outcome_consistent,
                spend,
                NULL
            )
        ) AS total_spend,

        AVG(
            IF(
                spend_eligible
                AND outcome_consistent,
                spend,
                NULL
            )
        ) AS mean_spend,

        STDDEV_SAMP(
            IF(
                spend_eligible
                AND outcome_consistent,
                spend,
                NULL
            )
        ) AS spend_sd

    FROM segment_membership

    GROUP BY
        segment_variable,
        segment_value,
        treatment_group
)

SELECT
    segment_variable,
    segment_value,

    treatment_group,

    CASE treatment_group
        WHEN 'control' THEN 1
        WHEN 'mens_email' THEN 2
        WHEN 'womens_email' THEN 3
        ELSE 99
    END AS treatment_order,

    segment_n,

    visit_n,
    visit_count,
    visit_rate,

    conversion_n,
    conversion_count,
    conversion_rate,

    spend_n,
    total_spend,
    mean_spend,
    spend_sd

FROM aggregated;


-- ============================================================
-- 1. Build descriptive Control-relative segment lifts
-- ============================================================
--
-- IMPORTANT:
--   These are raw point estimates only.
--
--   They are NOT yet evidence of heterogeneous treatment effects.
--
--   For example:
--
--       ATE(segment A) > ATE(segment B)
--
--   does NOT by itself imply that the treatment effect differs
--   statistically between segment A and segment B.
--
--   Formal interaction / heterogeneity inference belongs in
--   src/heterogeneity.py.
-- ============================================================

CREATE OR REPLACE TABLE `ceus.segment_lifts` AS

WITH control AS (

    SELECT
        segment_variable,
        segment_value,

        segment_n AS control_n,

        visit_rate AS control_visit_rate,
        conversion_rate AS control_conversion_rate,
        mean_spend AS control_mean_spend

    FROM `ceus.segment_metrics`

    WHERE treatment_group = 'control'
),

treatments AS (

    SELECT
        segment_variable,
        segment_value,
        treatment_group,

        segment_n AS treatment_n,

        visit_rate AS treatment_visit_rate,
        conversion_rate AS treatment_conversion_rate,
        mean_spend AS treatment_mean_spend

    FROM `ceus.segment_metrics`

    WHERE treatment_group IN (
        'mens_email',
        'womens_email'
    )
)

SELECT
    t.segment_variable,
    t.segment_value,
    t.treatment_group,

    c.control_n,
    t.treatment_n,

    -- --------------------------------------------------------
    -- Visit
    -- --------------------------------------------------------
    c.control_visit_rate,
    t.treatment_visit_rate,

    (
        t.treatment_visit_rate
        - c.control_visit_rate
    ) AS visit_ate,

    SAFE_DIVIDE(
        t.treatment_visit_rate
        - c.control_visit_rate,
        c.control_visit_rate
    ) AS visit_relative_lift,


    -- --------------------------------------------------------
    -- Conversion
    -- --------------------------------------------------------
    c.control_conversion_rate,
    t.treatment_conversion_rate,

    (
        t.treatment_conversion_rate
        - c.control_conversion_rate
    ) AS conversion_ate,

    SAFE_DIVIDE(
        t.treatment_conversion_rate
        - c.control_conversion_rate,
        c.control_conversion_rate
    ) AS conversion_relative_lift,


    -- --------------------------------------------------------
    -- Spend
    -- --------------------------------------------------------
    c.control_mean_spend,
    t.treatment_mean_spend,

    (
        t.treatment_mean_spend
        - c.control_mean_spend
    ) AS spend_ate,

    SAFE_DIVIDE(
        t.treatment_mean_spend
        - c.control_mean_spend,
        c.control_mean_spend
    ) AS spend_relative_lift

FROM treatments AS t

INNER JOIN control AS c
    USING (
        segment_variable,
        segment_value
    );


-- ============================================================
-- 2. Segment coverage validation
-- ============================================================

SELECT
    segment_variable,

    COUNT(DISTINCT segment_value)
        AS segment_value_count,

    COUNT(DISTINCT treatment_group)
        AS treatment_arm_count,

    SUM(segment_n)
        AS rows_across_arms

FROM `ceus.segment_metrics`

GROUP BY segment_variable

ORDER BY segment_variable;


-- ============================================================
-- 3. Treatment completeness by segment value
-- ============================================================
--
-- Every segment value should normally contain all 3 randomized arms.
-- ============================================================

SELECT
    segment_variable,
    segment_value,

    COUNT(DISTINCT treatment_group)
        AS treatment_arm_count,

    COUNTIF(treatment_group = 'control')
        AS control_arm_count,

    COUNTIF(treatment_group = 'mens_email')
        AS mens_email_arm_count,

    COUNTIF(treatment_group = 'womens_email')
        AS womens_email_arm_count

FROM `ceus.segment_metrics`

GROUP BY
    segment_variable,
    segment_value

HAVING COUNT(DISTINCT treatment_group) != 3

ORDER BY
    segment_variable,
    segment_value;


-- ============================================================
-- 4. Metric denominator validation
-- ============================================================
--
-- Current audited data should have zero exclusions.
-- ============================================================

SELECT
    SUM(segment_n - visit_n)
        AS visit_excluded_rows,

    SUM(segment_n - conversion_n)
        AS conversion_excluded_rows,

    SUM(segment_n - spend_n)
        AS spend_excluded_rows

FROM `ceus.segment_metrics`;


-- ============================================================
-- 5. Small-cell diagnostic
-- ============================================================
--
-- Do NOT automatically remove small cells here.
--
-- Small segment-arm cells should be handled explicitly during
-- heterogeneity inference because unstable estimates can create
-- misleading apparent treatment-effect variation.
-- ============================================================

SELECT
    segment_variable,
    segment_value,
    treatment_group,
    segment_n

FROM `ceus.segment_metrics`

WHERE segment_n < 100

ORDER BY
    segment_n,
    segment_variable,
    segment_value,
    treatment_group;


-- ============================================================
-- 6. Compact descriptive lift table
-- ============================================================

SELECT
    segment_variable,
    segment_value,
    treatment_group,

    control_n,
    treatment_n,

    ROUND(
        visit_ate,
        6
    ) AS visit_ate,

    ROUND(
        conversion_ate,
        6
    ) AS conversion_ate,

    ROUND(
        spend_ate,
        6
    ) AS spend_ate

FROM `ceus.segment_lifts`

ORDER BY
    segment_variable,
    segment_value,
    CASE treatment_group
        WHEN 'mens_email' THEN 1
        WHEN 'womens_email' THEN 2
        ELSE 99
    END;


-- ============================================================
-- Interpretation guardrails
-- ============================================================
--
-- Correct interpretation:
--
--   "Within segment X, the observed Men's Email minus Control
--    spend difference was Y."
--
--
-- Incorrect interpretation at this stage:
--
--   "Segment X responds significantly better than segment Y."
--
--
-- To establish treatment-effect heterogeneity, downstream analysis
-- must directly test interaction / effect differences, e.g.:
--
--   Y = beta0
--       + beta1 * Treatment
--       + beta2 * Segment
--       + beta3 * Treatment * Segment
--       + error
--
-- where beta3 represents treatment-effect heterogeneity.
--
--
-- Do not segment on post-treatment variables:
--
--   visit
--   conversion
--   spend
--
-- ============================================================