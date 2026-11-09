-- Cover purchase, promised, and actual delivery dates, plus a key for unknown dates.
CREATE OR REPLACE TABLE `${PROJECT}.${WAREHOUSE}.dim_date` AS
WITH relevant_dates AS (
    SELECT purchase_date AS calendar_date FROM `${PROJECT}.${WAREHOUSE}.prepared_orders`
    UNION ALL
    SELECT delivered_date FROM `${PROJECT}.${WAREHOUSE}.prepared_orders`
    UNION ALL
    SELECT estimated_delivery_date FROM `${PROJECT}.${WAREHOUSE}.prepared_orders`
), bounds AS (
    -- Find the first and last relevant day, including promised delivery dates.
    SELECT MIN(calendar_date) AS first_date, MAX(calendar_date) AS last_date
    FROM relevant_dates
), calendar AS (
    -- Include days with no orders so the date dimension has no gaps.
    SELECT calendar_date
    FROM bounds, UNNEST(GENERATE_DATE_ARRAY(first_date, last_date)) AS calendar_date
)
SELECT CAST(FORMAT_DATE('%Y%m%d', calendar_date) AS INT64) AS date_key,
       calendar_date AS date, EXTRACT(YEAR FROM calendar_date) AS year,
       EXTRACT(QUARTER FROM calendar_date) AS quarter,
       EXTRACT(MONTH FROM calendar_date) AS month,
       FORMAT_DATE('%B', calendar_date) AS month_name,
       EXTRACT(DAYOFWEEK FROM calendar_date) AS weekday_number,
       FORMAT_DATE('%A', calendar_date) AS weekday_name
FROM calendar
-- Key zero represents an item whose purchase date is unavailable.
UNION ALL
SELECT 0, CAST(NULL AS DATE), CAST(NULL AS INT64), CAST(NULL AS INT64),
       CAST(NULL AS INT64), 'unknown', CAST(NULL AS INT64), 'unknown';
