-- Does lateness hurt reviews within every state, or only in distant regions?
-- If late orders score lower than on-time orders inside each state, geography
-- and distance cannot be the main explanation for the review gap.
-- Uses fact_order_item grouped by order_id (one row per order per state)
-- so order-level review scores are not inflated by item count.
WITH orders AS (
  SELECT f.order_id,
         ANY_VALUE(f.review_score)    AS score,
         ANY_VALUE(f.is_late)         AS is_late,
         ANY_VALUE(c.customer_state)  AS state
  FROM `${PROJECT}.${WAREHOUSE}.fact_order_item` AS f
  JOIN `${PROJECT}.${WAREHOUSE}.dim_customer`    AS c USING (customer_key)
  WHERE f.review_score IS NOT NULL
    AND f.is_delivered
  GROUP BY f.order_id
)
SELECT
  state                                                                 AS customer_state,
  COUNT(*)                                                              AS orders,
  ROUND(AVG(CAST(is_late AS INT64)), 4)                                AS late_rate,
  ROUND(AVG(IF(NOT is_late, score, NULL)), 3)                          AS avg_score_on_time,
  ROUND(AVG(IF(    is_late, score, NULL)), 3)                          AS avg_score_late,
  ROUND(AVG(IF(NOT is_late, score, NULL))
      - AVG(IF(    is_late, score, NULL)), 3)                          AS score_penalty
FROM orders
GROUP BY state
HAVING COUNT(*) >= 100
ORDER BY late_rate DESC;
