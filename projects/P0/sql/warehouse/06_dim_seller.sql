-- Simulate a quarterly review policy; this is not a historical Olist intervention.
-- Watchlist: previous quarter had >=20 delivered items and >=15% late items.
-- Evidence is grouped by delivery date, so the tier uses only completed deliveries.
-- Intervals are half-open: effective_from <= purchase_date < effective_to.
CREATE OR REPLACE TABLE `${PROJECT}.${WAREHOUSE}.dim_seller` AS
WITH observed_dates AS (
    SELECT purchase_date AS event_date FROM `${PROJECT}.${WAREHOUSE}.prepared_orders`
    UNION ALL
    SELECT delivered_date FROM `${PROJECT}.${WAREHOUSE}.prepared_orders`
), bounds AS (
    SELECT DATE_TRUNC(MIN(event_date), QUARTER) AS first_quarter,
           DATE_TRUNC(MAX(event_date), QUARTER) AS last_quarter
    FROM observed_dates
), quarters AS (
    -- Create one date for the start of each quarter in the available history.
    SELECT quarter_start
    FROM bounds, UNNEST(GENERATE_DATE_ARRAY(first_quarter, last_quarter, INTERVAL 3 MONTH)) AS quarter_start
), tiers AS (
    -- Check every seller each quarter using only the previous quarter's deliveries.
    SELECT s.seller_id, q.quarter_start,
           CASE WHEN p.delivered_items >= 20 AND p.late_rate >= 0.15
                THEN 'Watchlist' ELSE 'Standard' END AS perf_tier
    FROM `${PROJECT}.${STAGING}.sellers` AS s
    CROSS JOIN quarters AS q
    LEFT JOIN `${PROJECT}.${WAREHOUSE}.seller_quarterly_performance` AS p
      ON p.seller_id = s.seller_id
     AND p.performance_quarter = DATE_SUB(q.quarter_start, INTERVAL 3 MONTH)
), with_previous AS (
    -- LAG looks at the previous quarter's tier so we can detect a change.
    SELECT *, LAG(perf_tier) OVER (PARTITION BY seller_id ORDER BY quarter_start) AS previous_tier
    FROM tiers
), changes AS (
    -- A new history row is needed only for the first tier or an actual change.
    SELECT seller_id, quarter_start AS effective_from, perf_tier
    FROM with_previous
    WHERE previous_tier IS NULL OR perf_tier != previous_tier
), periods AS (
    -- LEAD finds the next version's start; that date closes this version.
    SELECT *, COALESCE(LEAD(effective_from) OVER (PARTITION BY seller_id ORDER BY effective_from),
                       DATE '9999-12-31') AS effective_to
    FROM changes
)
-- The version start is part of the key, so one seller can have several historical keys.
SELECT TO_HEX(SHA256(CONCAT('seller|', p.seller_id, '|', CAST(p.effective_from AS STRING)))) AS seller_key,
       p.seller_id, s.seller_state, s.seller_city, s.seller_zip_code_prefix,
       p.perf_tier, p.effective_from, p.effective_to,
       p.effective_to = DATE '9999-12-31' AS is_current
FROM periods AS p
JOIN `${PROJECT}.${STAGING}.sellers` AS s USING (seller_id)
UNION ALL
SELECT 'unknown', CAST(NULL AS STRING), 'unknown', 'unknown', CAST(NULL AS STRING),
       'Unknown', DATE '0001-01-01', DATE '9999-12-31', TRUE;
