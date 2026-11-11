-- Q4: How does freight charged relative to item price relate to customer satisfaction?
-- Pearson correlation between order_freight_ratio and review_score at the order level.
-- Deduplicate the fact/date join so multi-item orders do not receive extra weight.
-- Freight ratio is total order freight charged divided by order merchandise value;
-- it is not the carrier's shipping cost and is not a proxy for lost revenue.
-- A negative correlation indicates association only; unmeasured factors such as
-- product quality and seller communication also drive review scores.

-- Correlation summary: reviewed delivered orders with known purchase dates and ratios.
WITH orders AS (
  SELECT DISTINCT f.order_id, f.order_freight_ratio, f.review_score
  FROM `${PROJECT}.${WAREHOUSE}.fact_order_item` AS f
  JOIN `${PROJECT}.${WAREHOUSE}.dim_date` AS d ON d.date_key = f.purchase_date_key
  WHERE f.is_delivered AND f.review_score IS NOT NULL
    AND f.order_freight_ratio IS NOT NULL AND d.date IS NOT NULL
)
SELECT
  ROUND(CORR(CAST(order_freight_ratio AS FLOAT64),
             CAST(review_score        AS FLOAT64)), 4) AS pearson_r,
  COUNT(*)                                             AS n
FROM orders;

-- Bucketed breakdown (run separately to see avg score per freight tier)
-- SELECT
--   CASE
--     WHEN order_freight_ratio < 0.1  THEN '< 10%'
--     WHEN order_freight_ratio < 0.2  THEN '10–20%'
--     WHEN order_freight_ratio < 0.4  THEN '20–40%'
--     WHEN order_freight_ratio < 0.7  THEN '40–70%'
--     ELSE                                 '>= 70%'
--   END AS freight_bucket,
--   COUNT(*) AS orders,
--   ROUND(AVG(CAST(review_score AS FLOAT64)), 3) AS avg_review_score
-- FROM `${PROJECT}.${WAREHOUSE}.order_delivery`
-- WHERE review_score IS NOT NULL AND order_freight_ratio IS NOT NULL AND is_delivered
-- GROUP BY freight_bucket
-- ORDER BY MIN(order_freight_ratio);
