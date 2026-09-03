-- BigQuery Standard SQL (GoogleSQL)
--
-- Data-quality audit for the raw Hillstrom experiment table.
--
-- Source table:
--   Replace `ceus.hillstrom_raw` with the actual BigQuery table
--   created from data/raw/Hillstrom.csv before running this script.
--
-- No project ID is configured in this repository, so `<PROJECT_ID>` is left as
-- an explicit placeholder rather than inventing one.
--
-- This script audits structural validity only. It does not estimate treatment
-- effects, test treatment significance, validate randomization, or draw
-- experiment conclusions.

-- ---------------------------------------------------------------------------
-- 0. Source
-- ---------------------------------------------------------------------------
-- The CSV header inspected locally is:
-- recency, history_segment, history, mens, womens, zip_code, newbie, channel,
-- segment, visit, conversion, spend
--
-- This temporary table is a session-scoped audit snapshot. It preserves the raw
-- source table and selects only the columns observed in data/raw/Hillstrom.csv.
CREATE TEMP TABLE audit_source AS
SELECT
  recency,
  history_segment,
  history,
  mens,
  womens,
  zip_code,
  newbie,
  channel,
  segment,
  visit,
  conversion,
  spend
FROM `ceus.hillstrom_raw`;

-- ---------------------------------------------------------------------------
-- 1. Dataset shape and analytical grain
-- ---------------------------------------------------------------------------
-- Observed grain: one row appears to represent one experimental unit/customer,
-- but row-level uniqueness cannot be proven from an explicit primary key.
WITH
  total_rows AS (
    SELECT COUNT(*) AS total_row_count
    FROM audit_source
  ),
  distinct_rows AS (
    SELECT COUNT(*) AS distinct_row_count
    FROM (
      SELECT DISTINCT
        recency,
        history_segment,
        history,
        mens,
        womens,
        zip_code,
        newbie,
        channel,
        segment,
        visit,
        conversion,
        spend
      FROM audit_source
    )
  )
SELECT
  total_row_count,
  distinct_row_count,
  total_row_count - distinct_row_count AS exact_duplicate_row_count,
  total_row_count > distinct_row_count AS has_exact_duplicate_rows,
  'Observed grain: one row appears to represent one experimental unit/customer, but row-level uniqueness cannot be proven from an explicit primary key.' AS grain_note
FROM total_rows
CROSS JOIN distinct_rows;

-- ---------------------------------------------------------------------------
-- 2. Missingness
-- ---------------------------------------------------------------------------
-- For string-compatible checks, blank strings are reported separately from SQL
-- NULLs because raw CSV imports can preserve blanks as empty strings.
WITH column_missingness AS (
  SELECT
    'recency' AS column_name,
    COUNT(*) AS total_rows,
    COUNTIF(recency IS NULL) AS null_count,
    COUNTIF(TRIM(CAST(recency AS STRING)) = '') AS blank_string_count,
    COUNTIF(recency IS NULL OR TRIM(CAST(recency AS STRING)) = '') AS missing_count
  FROM audit_source
  UNION ALL
  SELECT
    'history_segment',
    COUNT(*),
    COUNTIF(history_segment IS NULL),
    COUNTIF(TRIM(CAST(history_segment AS STRING)) = ''),
    COUNTIF(history_segment IS NULL OR TRIM(CAST(history_segment AS STRING)) = '')
  FROM audit_source
  UNION ALL
  SELECT
    'history',
    COUNT(*),
    COUNTIF(history IS NULL),
    COUNTIF(TRIM(CAST(history AS STRING)) = ''),
    COUNTIF(history IS NULL OR TRIM(CAST(history AS STRING)) = '')
  FROM audit_source
  UNION ALL
  SELECT
    'mens',
    COUNT(*),
    COUNTIF(mens IS NULL),
    COUNTIF(TRIM(CAST(mens AS STRING)) = ''),
    COUNTIF(mens IS NULL OR TRIM(CAST(mens AS STRING)) = '')
  FROM audit_source
  UNION ALL
  SELECT
    'womens',
    COUNT(*),
    COUNTIF(womens IS NULL),
    COUNTIF(TRIM(CAST(womens AS STRING)) = ''),
    COUNTIF(womens IS NULL OR TRIM(CAST(womens AS STRING)) = '')
  FROM audit_source
  UNION ALL
  SELECT
    'zip_code',
    COUNT(*),
    COUNTIF(zip_code IS NULL),
    COUNTIF(TRIM(CAST(zip_code AS STRING)) = ''),
    COUNTIF(zip_code IS NULL OR TRIM(CAST(zip_code AS STRING)) = '')
  FROM audit_source
  UNION ALL
  SELECT
    'newbie',
    COUNT(*),
    COUNTIF(newbie IS NULL),
    COUNTIF(TRIM(CAST(newbie AS STRING)) = ''),
    COUNTIF(newbie IS NULL OR TRIM(CAST(newbie AS STRING)) = '')
  FROM audit_source
  UNION ALL
  SELECT
    'channel',
    COUNT(*),
    COUNTIF(channel IS NULL),
    COUNTIF(TRIM(CAST(channel AS STRING)) = ''),
    COUNTIF(channel IS NULL OR TRIM(CAST(channel AS STRING)) = '')
  FROM audit_source
  UNION ALL
  SELECT
    'segment',
    COUNT(*),
    COUNTIF(segment IS NULL),
    COUNTIF(TRIM(CAST(segment AS STRING)) = ''),
    COUNTIF(segment IS NULL OR TRIM(CAST(segment AS STRING)) = '')
  FROM audit_source
  UNION ALL
  SELECT
    'visit',
    COUNT(*),
    COUNTIF(visit IS NULL),
    COUNTIF(TRIM(CAST(visit AS STRING)) = ''),
    COUNTIF(visit IS NULL OR TRIM(CAST(visit AS STRING)) = '')
  FROM audit_source
  UNION ALL
  SELECT
    'conversion',
    COUNT(*),
    COUNTIF(conversion IS NULL),
    COUNTIF(TRIM(CAST(conversion AS STRING)) = ''),
    COUNTIF(conversion IS NULL OR TRIM(CAST(conversion AS STRING)) = '')
  FROM audit_source
  UNION ALL
  SELECT
    'spend',
    COUNT(*),
    COUNTIF(spend IS NULL),
    COUNTIF(TRIM(CAST(spend AS STRING)) = ''),
    COUNTIF(spend IS NULL OR TRIM(CAST(spend AS STRING)) = '')
  FROM audit_source
)
SELECT
  column_name,
  total_rows,
  null_count,
  ROUND(100 * SAFE_DIVIDE(null_count, total_rows), 4) AS null_percentage,
  blank_string_count,
  ROUND(100 * SAFE_DIVIDE(blank_string_count, total_rows), 4) AS blank_string_percentage,
  missing_count,
  ROUND(100 * SAFE_DIVIDE(missing_count, total_rows), 4) AS missing_percentage
FROM column_missingness
ORDER BY column_name;

-- ---------------------------------------------------------------------------
-- 3. Treatment domain integrity
-- ---------------------------------------------------------------------------
-- This is a structural treatment-label check only. Similar treatment counts
-- must not be interpreted here as evidence that randomization succeeded.
WITH
  total_rows AS (
    SELECT COUNT(*) AS total_row_count
    FROM audit_source
  ),
  treatment_values AS (
    SELECT
      CASE
        WHEN segment IS NULL THEN '<NULL>'
        WHEN TRIM(CAST(segment AS STRING)) = '' THEN '<BLANK>'
        ELSE TRIM(CAST(segment AS STRING))
      END AS segment_value,
      CASE
        WHEN segment IS NULL OR TRIM(CAST(segment AS STRING)) = '' THEN 'missing'
        WHEN TRIM(CAST(segment AS STRING)) IN (
          'No E-Mail',
          'Mens E-Mail',
          'Womens E-Mail'
        ) THEN 'expected'
        ELSE 'unexpected'
      END AS domain_status
    FROM audit_source
  )
SELECT
  segment_value,
  domain_status,
  COUNT(*) AS row_count,
  ROUND(100 * SAFE_DIVIDE(COUNT(*), ANY_VALUE(total_row_count)), 4) AS percentage_of_total
FROM treatment_values
CROSS JOIN total_rows
GROUP BY segment_value, domain_status
ORDER BY domain_status DESC, segment_value;

-- ---------------------------------------------------------------------------
-- 4. Binary variable integrity
-- ---------------------------------------------------------------------------
-- Binary values are checked as raw display values so invalid values are not
-- coerced away during audit.
WITH
  binary_values AS (
    SELECT 'mens' AS variable_name, CAST(mens AS STRING) AS raw_value
    FROM audit_source
    UNION ALL
    SELECT 'womens', CAST(womens AS STRING)
    FROM audit_source
    UNION ALL
    SELECT 'newbie', CAST(newbie AS STRING)
    FROM audit_source
    UNION ALL
    SELECT 'visit', CAST(visit AS STRING)
    FROM audit_source
    UNION ALL
    SELECT 'conversion', CAST(conversion AS STRING)
    FROM audit_source
  ),
  labeled_values AS (
    SELECT
      variable_name,
      raw_value,
      CASE
        WHEN raw_value IS NULL THEN '<NULL>'
        WHEN TRIM(raw_value) = '' THEN '<BLANK>'
        ELSE TRIM(raw_value)
      END AS display_value,
      CASE
        WHEN raw_value IS NULL OR TRIM(raw_value) = '' THEN 'missing'
        WHEN TRIM(raw_value) IN ('0', '1') THEN 'expected'
        ELSE 'unexpected'
      END AS domain_status
    FROM binary_values
  )
SELECT
  variable_name,
  ARRAY_AGG(DISTINCT display_value ORDER BY display_value) AS distinct_values,
  COUNT(*) AS total_rows,
  COUNTIF(raw_value IS NULL) AS null_count,
  COUNTIF(raw_value IS NOT NULL AND TRIM(raw_value) = '') AS blank_string_count,
  COUNTIF(
    raw_value IS NOT NULL
    AND TRIM(raw_value) != ''
    AND TRIM(raw_value) NOT IN ('0', '1')
  ) AS invalid_value_count
FROM labeled_values
GROUP BY variable_name
ORDER BY variable_name;

WITH
  binary_values AS (
    SELECT 'mens' AS variable_name, CAST(mens AS STRING) AS raw_value
    FROM audit_source
    UNION ALL
    SELECT 'womens', CAST(womens AS STRING)
    FROM audit_source
    UNION ALL
    SELECT 'newbie', CAST(newbie AS STRING)
    FROM audit_source
    UNION ALL
    SELECT 'visit', CAST(visit AS STRING)
    FROM audit_source
    UNION ALL
    SELECT 'conversion', CAST(conversion AS STRING)
    FROM audit_source
  ),
  labeled_values AS (
    SELECT
      variable_name,
      CASE
        WHEN raw_value IS NULL THEN '<NULL>'
        WHEN TRIM(raw_value) = '' THEN '<BLANK>'
        ELSE TRIM(raw_value)
      END AS display_value,
      CASE
        WHEN raw_value IS NULL OR TRIM(raw_value) = '' THEN 'missing'
        WHEN TRIM(raw_value) IN ('0', '1') THEN 'expected'
        ELSE 'unexpected'
      END AS domain_status
    FROM binary_values
  ),
  total_rows AS (
    SELECT COUNT(*) AS total_row_count
    FROM audit_source
  )
SELECT
  variable_name,
  display_value,
  domain_status,
  COUNT(*) AS row_count,
  ROUND(100 * SAFE_DIVIDE(COUNT(*), ANY_VALUE(total_row_count)), 4) AS percentage_of_rows
FROM labeled_values
CROSS JOIN total_rows
GROUP BY variable_name, display_value, domain_status
ORDER BY variable_name, display_value;

-- ---------------------------------------------------------------------------
-- 5. Numeric range and sanity checks
-- ---------------------------------------------------------------------------
-- Large values are exposed for downstream review, not classified as outliers.
WITH
  numeric_values AS (
    SELECT
      'recency' AS variable_name,
      CAST(recency AS STRING) AS raw_value,
      SAFE_CAST(CAST(recency AS STRING) AS FLOAT64) AS numeric_value
    FROM audit_source
    UNION ALL
    SELECT
      'history',
      CAST(history AS STRING),
      SAFE_CAST(CAST(history AS STRING) AS FLOAT64)
    FROM audit_source
    UNION ALL
    SELECT
      'spend',
      CAST(spend AS STRING),
      SAFE_CAST(CAST(spend AS STRING) AS FLOAT64)
    FROM audit_source
  ),
  numeric_profile AS (
    SELECT
      variable_name,
      COUNT(*) AS rows_evaluated,
      COUNTIF(raw_value IS NULL) AS null_count,
      COUNTIF(raw_value IS NOT NULL AND TRIM(raw_value) = '') AS blank_string_count,
      COUNTIF(
        raw_value IS NOT NULL
        AND TRIM(raw_value) != ''
        AND numeric_value IS NULL
      ) AS non_numeric_count,
      COUNTIF(numeric_value IS NOT NULL) AS numeric_count,
      MIN(numeric_value) AS min_value,
      MAX(numeric_value) AS max_value,
      AVG(numeric_value) AS mean_value,
      APPROX_QUANTILES(numeric_value, 100) AS approx_quantiles,
      COUNTIF(numeric_value < 0) AS negative_value_count
    FROM numeric_values
    GROUP BY variable_name
  )
SELECT
  variable_name,
  rows_evaluated,
  numeric_count,
  null_count,
  blank_string_count,
  non_numeric_count,
  min_value,
  max_value,
  mean_value,
  approx_quantiles[SAFE_OFFSET(25)] AS approx_p25,
  approx_quantiles[SAFE_OFFSET(50)] AS approx_median,
  approx_quantiles[SAFE_OFFSET(75)] AS approx_p75,
  approx_quantiles[SAFE_OFFSET(90)] AS approx_p90,
  approx_quantiles[SAFE_OFFSET(95)] AS approx_p95,
  approx_quantiles[SAFE_OFFSET(99)] AS approx_p99,
  negative_value_count
FROM numeric_profile
ORDER BY variable_name;

-- ---------------------------------------------------------------------------
-- 6. Categorical domain checks
-- ---------------------------------------------------------------------------
-- The source data spells one zip_code value as "Surburban"; this audit preserves
-- that raw category rather than correcting it.
WITH
  categorical_values AS (
    SELECT 'channel' AS variable_name, CAST(channel AS STRING) AS raw_value
    FROM audit_source
    UNION ALL
    SELECT 'zip_code', CAST(zip_code AS STRING)
    FROM audit_source
    UNION ALL
    SELECT 'history_segment', CAST(history_segment AS STRING)
    FROM audit_source
  ),
  labeled_values AS (
    SELECT
      variable_name,
      raw_value,
      CASE
        WHEN raw_value IS NULL THEN '<NULL>'
        WHEN TRIM(raw_value) = '' THEN '<BLANK>'
        ELSE TRIM(raw_value)
      END AS category_value,
      CASE
        WHEN raw_value IS NULL OR TRIM(raw_value) = '' THEN 'missing'
        WHEN variable_name = 'channel'
          AND TRIM(raw_value) IN ('Phone', 'Web', 'Multichannel') THEN 'expected'
        WHEN variable_name = 'zip_code'
          AND TRIM(raw_value) IN ('Rural', 'Surburban', 'Urban') THEN 'expected'
        WHEN variable_name = 'history_segment'
          AND TRIM(raw_value) IN (
            '1) $0 - $100',
            '2) $100 - $200',
            '3) $200 - $350',
            '4) $350 - $500',
            '5) $500 - $750',
            '6) $750 - $1,000',
            '7) $1,000 +'
          ) THEN 'expected'
        ELSE 'unexpected'
      END AS domain_status
    FROM categorical_values
  ),
  totals AS (
    SELECT
      variable_name,
      COUNT(*) AS variable_row_count
    FROM labeled_values
    GROUP BY variable_name
  )
SELECT
  labeled_values.variable_name,
  labeled_values.category_value,
  labeled_values.domain_status,
  COUNT(*) AS row_count,
  ROUND(100 * SAFE_DIVIDE(COUNT(*), ANY_VALUE(totals.variable_row_count)), 4) AS percentage_of_variable
FROM labeled_values
JOIN totals
  USING (variable_name)
GROUP BY
  labeled_values.variable_name,
  labeled_values.category_value,
  labeled_values.domain_status
ORDER BY
  labeled_values.variable_name,
  labeled_values.domain_status DESC,
  row_count DESC,
  labeled_values.category_value;

-- ---------------------------------------------------------------------------
-- 7. Outcome consistency
-- ---------------------------------------------------------------------------
-- These checks expose logical issues only. They do not remove rows or interpret
-- campaign performance.
WITH typed_outcomes AS (
  SELECT
    SAFE_CAST(CAST(visit AS STRING) AS INT64) AS visit_value,
    SAFE_CAST(CAST(conversion AS STRING) AS INT64) AS conversion_value,
    SAFE_CAST(CAST(spend AS STRING) AS FLOAT64) AS spend_value
  FROM audit_source
)
SELECT
  'conversion = 1 AND spend <= 0' AS condition_checked,
  COUNTIF(conversion_value = 1 AND spend_value <= 0) AS row_count
FROM typed_outcomes
UNION ALL
SELECT
  'conversion = 0 AND spend > 0',
  COUNTIF(conversion_value = 0 AND spend_value > 0)
FROM typed_outcomes
UNION ALL
SELECT
  'conversion = 1 AND visit = 0',
  COUNTIF(conversion_value = 1 AND visit_value = 0)
FROM typed_outcomes
UNION ALL
SELECT
  'spend < 0',
  COUNTIF(spend_value < 0)
FROM typed_outcomes;

-- ---------------------------------------------------------------------------
-- 9. Final audit summary query
-- ---------------------------------------------------------------------------
WITH
  distinct_rows AS (
    SELECT COUNT(*) AS distinct_row_count
    FROM (
      SELECT DISTINCT
        recency,
        history_segment,
        history,
        mens,
        womens,
        zip_code,
        newbie,
        channel,
        segment,
        visit,
        conversion,
        spend
      FROM audit_source
    )
  ),
  row_flags AS (
    SELECT
      (
        recency IS NULL OR TRIM(CAST(recency AS STRING)) = ''
        OR history_segment IS NULL OR TRIM(CAST(history_segment AS STRING)) = ''
        OR history IS NULL OR TRIM(CAST(history AS STRING)) = ''
        OR mens IS NULL OR TRIM(CAST(mens AS STRING)) = ''
        OR womens IS NULL OR TRIM(CAST(womens AS STRING)) = ''
        OR zip_code IS NULL OR TRIM(CAST(zip_code AS STRING)) = ''
        OR newbie IS NULL OR TRIM(CAST(newbie AS STRING)) = ''
        OR channel IS NULL OR TRIM(CAST(channel AS STRING)) = ''
        OR segment IS NULL OR TRIM(CAST(segment AS STRING)) = ''
        OR visit IS NULL OR TRIM(CAST(visit AS STRING)) = ''
        OR conversion IS NULL OR TRIM(CAST(conversion AS STRING)) = ''
        OR spend IS NULL OR TRIM(CAST(spend AS STRING)) = ''
      ) AS has_any_missing_value,
      (
        segment IS NULL
        OR TRIM(CAST(segment AS STRING)) = ''
        OR TRIM(CAST(segment AS STRING)) NOT IN (
          'No E-Mail',
          'Mens E-Mail',
          'Womens E-Mail'
        )
      ) AS has_invalid_treatment_value,
      (
        IF(
          mens IS NOT NULL
          AND TRIM(CAST(mens AS STRING)) != ''
          AND TRIM(CAST(mens AS STRING)) NOT IN ('0', '1'),
          1,
          0
        )
        + IF(
          womens IS NOT NULL
          AND TRIM(CAST(womens AS STRING)) != ''
          AND TRIM(CAST(womens AS STRING)) NOT IN ('0', '1'),
          1,
          0
        )
        + IF(
          newbie IS NOT NULL
          AND TRIM(CAST(newbie AS STRING)) != ''
          AND TRIM(CAST(newbie AS STRING)) NOT IN ('0', '1'),
          1,
          0
        )
        + IF(
          visit IS NOT NULL
          AND TRIM(CAST(visit AS STRING)) != ''
          AND TRIM(CAST(visit AS STRING)) NOT IN ('0', '1'),
          1,
          0
        )
        + IF(
          conversion IS NOT NULL
          AND TRIM(CAST(conversion AS STRING)) != ''
          AND TRIM(CAST(conversion AS STRING)) NOT IN ('0', '1'),
          1,
          0
        )
      ) AS invalid_binary_cell_count,
      (
        SAFE_CAST(CAST(conversion AS STRING) AS INT64) = 1
        AND SAFE_CAST(CAST(spend AS STRING) AS FLOAT64) <= 0
      )
      OR (
        SAFE_CAST(CAST(conversion AS STRING) AS INT64) = 0
        AND SAFE_CAST(CAST(spend AS STRING) AS FLOAT64) > 0
      )
      OR (
        SAFE_CAST(CAST(conversion AS STRING) AS INT64) = 1
        AND SAFE_CAST(CAST(visit AS STRING) AS INT64) = 0
      )
      OR SAFE_CAST(CAST(spend AS STRING) AS FLOAT64) < 0
        AS has_logically_inconsistent_outcome
    FROM audit_source
  )
SELECT
  COUNT(*) AS total_rows,
  ANY_VALUE(distinct_row_count) AS distinct_rows,
  COUNT(*) - ANY_VALUE(distinct_row_count) AS exact_duplicate_row_count,
  COUNTIF(has_any_missing_value) AS rows_with_any_missing_values,
  COUNTIF(has_invalid_treatment_value) AS invalid_treatment_rows,
  SUM(invalid_binary_cell_count) AS invalid_binary_cell_count,
  COUNTIF(invalid_binary_cell_count > 0) AS rows_with_invalid_binary_values,
  COUNTIF(has_logically_inconsistent_outcome) AS logically_inconsistent_outcome_rows
FROM row_flags
CROSS JOIN distinct_rows;

-- ---------------------------------------------------------------------------
-- 8. Pre-treatment vs post-treatment variable classification
-- ---------------------------------------------------------------------------
-- Treatment:
-- - segment
--
-- Pre-treatment covariates:
-- - recency
-- - history
-- - history_segment
-- - mens
-- - womens
-- - zip_code
-- - newbie
-- - channel
--
-- Post-treatment outcomes:
-- - visit
-- - conversion
-- - spend
--
-- Later randomization checks must use only pre-treatment covariates.
