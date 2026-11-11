-- Q3: Are delivery promises too optimistic in some customer regions?
-- avg_days_late > 0 means orders in that state arrive later than promised on average.
-- Compare promised and actual durations alongside late rates; an early average
-- can coexist with a substantial late tail. Include all delivered orders, reviewed or not.
-- Deduplicate the fact/customer join before calculating order-level averages.
-- States with fewer than 100 delivered orders are excluded.
WITH orders AS (
  SELECT DISTINCT f.order_id, c.customer_state, f.promise_days,
                  f.delivery_days, f.days_late, f.is_late
  FROM `${PROJECT}.${WAREHOUSE}.fact_order_item` AS f
  JOIN `${PROJECT}.${WAREHOUSE}.dim_customer` AS c USING (customer_key)
  WHERE f.is_delivered AND c.customer_state NOT IN ('unknown', 'Unknown')
)
SELECT
  customer_state,
  COUNT(*)                            AS delivered_orders,
  ROUND(AVG(promise_days),  1)     AS avg_promise_days,
  ROUND(AVG(delivery_days), 1)     AS avg_delivery_days,
  ROUND(AVG(days_late),     2)     AS avg_days_late,
  ROUND(SAFE_DIVIDE(COUNTIF(is_late), COUNT(*)), 4) AS late_rate
FROM orders
GROUP BY customer_state
HAVING delivered_orders >= 100
ORDER BY avg_days_late DESC;
