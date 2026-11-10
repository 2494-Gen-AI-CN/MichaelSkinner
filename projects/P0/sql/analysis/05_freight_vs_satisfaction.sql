-- Q4: How does freight charged relative to item price relate to customer satisfaction?
-- Pearson correlation between order_freight_ratio and review_score at the order level.
-- order_delivery supplies one row per order so the ratio and score are not inflated
-- by multi-item orders.  Freight ratio is the carrier charge divided by item price;
-- it is not the platform's cost and is not a proxy for lost revenue.
-- A negative correlation indicates association only; unmeasured factors such as
-- product quality and seller communication also drive review scores.

-- Correlation summary
SELECT
  ROUND(CORR(CAST(order_freight_ratio AS FLOAT64),
             CAST(review_score        AS FLOAT64)), 4) AS pearson_r,
  COUNT(*)                                             AS n
FROM `${PROJECT}.${WAREHOUSE}.order_delivery`
WHERE review_score        IS NOT NULL
  AND order_freight_ratio IS NOT NULL
  AND is_delivered;

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
