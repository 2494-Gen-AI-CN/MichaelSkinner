-- customer_id identifies an order's customer record; customer_unique_id can repeat.
CREATE OR REPLACE TABLE `${PROJECT}.${WAREHOUSE}.dim_customer` AS
SELECT TO_HEX(SHA256(CONCAT('customer|', customer_id))) AS customer_key,
       customer_id, customer_unique_id,
       customer_state, customer_city, customer_zip_code_prefix
FROM `${PROJECT}.${STAGING}.customers`
UNION ALL
SELECT 'unknown', CAST(NULL AS STRING), CAST(NULL AS STRING),
       'unknown', 'unknown', CAST(NULL AS STRING);
