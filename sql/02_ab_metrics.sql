-- ============================================================
-- Hillstrom A/B Test Metrics
-- Google BigQuery Standard SQL (GoogleSQL)
-- ============================================================
--
-- Purpose:
--   Construct treatment-arm-level outcome metrics for the Hillstrom
--   randomized email experiment.
--
-- This file defines descriptive experiment metrics only.
--
-- Statistical inference belongs in:
--   src/estimate_ate.py
--
-- Do NOT calculate here:
--   - p-values
--   - confidence intervals
--   - hypothesis-test decisions
--   - multiple-testing corrections
--   - bootstrap estimates
--
-- Upstream:
--   `ceus.experiment_population`
--
-- Output:
--   `ceus.ab_metrics`
--
-- Experimental arms:
--   control
--   mens_email
--   womens_email
--
-- Primary outcomes:
--   visit
--   conversion
--   spend
--
-- Important:
--   Spend is analyzed as spend per randomized user, including zeros.
--
--   Do NOT condition the primary spend outcome on conversion because
--   conversion is itself a post-treatment outcome. Conditioning on
--   converters would change the estimand and introduce post-treatment
--   selection.
-- ============================================================


-- ============================================================
-- 0. Build canonical treatment-arm metrics
-- ============================================================

CREATE OR REPLACE TABLE `ceus.ab_metrics` AS

WITH arm_aggregates AS (

    SELECT
        treatment_group,

        -- ----------------------------------------------------
        -- Treatment arm ordering
        -- ----------------------------------------------------
        CASE treatment_group
            WHEN 'control' THEN 1
            WHEN 'mens_email' THEN 2
            WHEN 'womens_email' THEN 3
            ELSE 99
        END AS treatment_order,

        -- ----------------------------------------------------
        -- Population
        -- ----------------------------------------------------
        COUNT(*) AS population_n,

        COUNTIF(
            experiment_eligible
        ) AS experiment_n,

        -- ----------------------------------------------------
        -- Visit outcome
        -- ----------------------------------------------------
        COUNTIF(
            experiment_eligible
            AND visit_eligible
        ) AS visit_n,

        COUNTIF(
            experiment_eligible
            AND visit_eligible
            AND visit = 1
        ) AS visit_count,

        AVG(
            IF(
                experiment_eligible
                AND visit_eligible,
                CAST(visit AS FLOAT64),
                NULL
            )
        ) AS visit_mean,

        STDDEV_SAMP(
            IF(
                experiment_eligible
                AND visit_eligible,
                CAST(visit AS FLOAT64),
                NULL
            )
        ) AS visit_sd,

        -- ----------------------------------------------------
        -- Conversion outcome
        -- ----------------------------------------------------
        COUNTIF(
            experiment_eligible
            AND conversion_eligible
        ) AS conversion_n,

        COUNTIF(
            experiment_eligible
            AND conversion_eligible
            AND conversion = 1
        ) AS conversion_count,

        AVG(
            IF(
                experiment_eligible
                AND conversion_eligible,
                CAST(conversion AS FLOAT64),
                NULL
            )
        ) AS conversion_mean,

        STDDEV_SAMP(
            IF(
                experiment_eligible
                AND conversion_eligible,
                CAST(conversion AS FLOAT64),
                NULL
            )
        ) AS conversion_sd,

        -- ----------------------------------------------------
        -- Spend outcome
        --
        -- Mean spend is calculated across all eligible randomized
        -- users, including zero-spend observations.
        -- ----------------------------------------------------
        COUNTIF(
            experiment_eligible
            AND spend_eligible
        ) AS spend_n,

        SUM(
            IF(
                experiment_eligible
                AND spend_eligible,
                spend,
                NULL
            )
        ) AS total_spend,

        AVG(
            IF(
                experiment_eligible
                AND spend_eligible,
                spend,
                NULL
            )
        ) AS mean_spend,

        STDDEV_SAMP(
            IF(
                experiment_eligible
                AND spend_eligible,
                spend,
                NULL
            )
        ) AS spend_sd

    FROM `ceus.experiment_population`

    GROUP BY treatment_group
)

SELECT
    treatment_group,
    treatment_order,

    -- Population
    population_n,
    experiment_n,

    -- Visit
    visit_n,
    visit_count,

    SAFE_DIVIDE(
        visit_count,
        visit_n
    ) AS visit_rate,

    visit_mean,
    visit_sd,

    -- Conversion
    conversion_n,
    conversion_count,

    SAFE_DIVIDE(
        conversion_count,
        conversion_n
    ) AS conversion_rate,

    conversion_mean,
    conversion_sd,

    -- Spend
    spend_n,
    total_spend,
    mean_spend,
    spend_sd

FROM arm_aggregates;


-- ============================================================
-- 1. Treatment-arm metrics
-- ============================================================

SELECT
    treatment_group,

    experiment_n,

    visit_n,
    visit_count,

    ROUND(
        100 * visit_rate,
        4
    ) AS visit_rate_pct,

    conversion_n,
    conversion_count,

    ROUND(
        100 * conversion_rate,
        4
    ) AS conversion_rate_pct,

    spend_n,

    ROUND(
        total_spend,
        2
    ) AS total_spend,

    ROUND(
        mean_spend,
        4
    ) AS mean_spend_per_user,

    ROUND(
        spend_sd,
        4
    ) AS spend_sd

FROM `ceus.ab_metrics`

ORDER BY treatment_order;


-- ============================================================
-- 2. Population accounting validation
-- ============================================================

SELECT
    SUM(population_n)
        AS total_population,

    SUM(experiment_n)
        AS total_experiment_n,

    SUM(visit_n)
        AS total_visit_n,

    SUM(conversion_n)
        AS total_conversion_n,

    SUM(spend_n)
        AS total_spend_n

FROM `ceus.ab_metrics`;


-- ============================================================
-- 3. Treatment-arm completeness validation
-- ============================================================

SELECT
    COUNT(*) AS treatment_arm_count,

    COUNTIF(
        treatment_group = 'control'
    ) AS control_arm_count,

    COUNTIF(
        treatment_group = 'mens_email'
    ) AS mens_email_arm_count,

    COUNTIF(
        treatment_group = 'womens_email'
    ) AS womens_email_arm_count,

    COUNTIF(
        treatment_group NOT IN (
            'control',
            'mens_email',
            'womens_email'
        )
        OR treatment_group IS NULL
    ) AS unexpected_arm_count

FROM `ceus.ab_metrics`;


-- ============================================================
-- 4. Metric denominator validation
-- ============================================================
--
-- With the current audited Hillstrom dataset, all values below
-- should be zero.
--
-- These checks are retained so that future source-data changes
-- cannot silently alter metric populations.
-- ============================================================

SELECT
    treatment_group,

    experiment_n - visit_n
        AS visit_excluded_n,

    experiment_n - conversion_n
        AS conversion_excluded_n,

    experiment_n - spend_n
        AS spend_excluded_n

FROM `ceus.ab_metrics`

ORDER BY treatment_order;


-- ============================================================
-- 5. Metric-domain validation
-- ============================================================

SELECT
    COUNTIF(
        visit_rate < 0
        OR visit_rate > 1
        OR visit_rate IS NULL
    ) AS invalid_visit_rate_rows,

    COUNTIF(
        conversion_rate < 0
        OR conversion_rate > 1
        OR conversion_rate IS NULL
    ) AS invalid_conversion_rate_rows,

    COUNTIF(
        mean_spend < 0
        OR mean_spend IS NULL
    ) AS invalid_mean_spend_rows,

    COUNTIF(
        total_spend < 0
        OR total_spend IS NULL
    ) AS invalid_total_spend_rows

FROM `ceus.ab_metrics`;


-- ============================================================
-- 6. Internal consistency validation
-- ============================================================

SELECT
    treatment_group,

    ABS(
        visit_rate - visit_mean
    ) AS visit_rate_mean_difference,

    ABS(
        conversion_rate - conversion_mean
    ) AS conversion_rate_mean_difference

FROM `ceus.ab_metrics`

ORDER BY treatment_order;


-- ============================================================
-- 7. Final compact experiment metric table
-- ============================================================

SELECT
    treatment_group,
    experiment_n AS n,

    ROUND(
        visit_rate,
        6
    ) AS visit_rate,

    ROUND(
        conversion_rate,
        6
    ) AS conversion_rate,

    ROUND(
        mean_spend,
        6
    ) AS mean_spend_per_user

FROM `ceus.ab_metrics`

ORDER BY treatment_order;


-- ============================================================
-- Estimands for downstream inference
-- ============================================================
--
-- Control:
--   T = control
--
-- Treatment 1:
--   T = mens_email
--
-- Treatment 2:
--   T = womens_email
--
--
-- Visit ITT:
--
--   tau_visit_mens
--     = E[visit | mens_email]
--       - E[visit | control]
--
--   tau_visit_womens
--     = E[visit | womens_email]
--       - E[visit | control]
--
--
-- Conversion ITT:
--
--   tau_conversion_mens
--     = E[conversion | mens_email]
--       - E[conversion | control]
--
--   tau_conversion_womens
--     = E[conversion | womens_email]
--       - E[conversion | control]
--
--
-- Spend ITT:
--
--   tau_spend_mens
--     = E[spend | mens_email]
--       - E[spend | control]
--
--   tau_spend_womens
--     = E[spend | womens_email]
--       - E[spend | control]
--
--
-- Statistical uncertainty for these estimands is intentionally
-- NOT calculated in SQL.
--
-- See:
--   src/estimate_ate.py
--
-- ============================================================