-- Q3: Are delivery promises too optimistic in some customer regions?
-- avg_days_late > 0 means orders in that state arrive later than promised on average.
-- Uses order_delivery (one row per order) for order-level averages.
-- States with fewer than 100 delivered orders are excluded.
SELECT
  dc.customer_state,
  COUNT(*)                            AS delivered_orders,
  ROUND(AVG(od.promise_days),  1)     AS avg_promise_days,
  ROUND(AVG(od.delivery_days), 1)     AS avg_delivery_days,
  ROUND(AVG(od.days_late),     2)     AS avg_days_late,
  ROUND(SAFE_DIVIDE(COUNTIF(od.is_late), COUNT(*)), 4) AS late_rate
FROM `${PROJECT}.${WAREHOUSE}.order_delivery` AS od
JOIN `${PROJECT}.${WAREHOUSE}.dim_customer`  AS dc USING (customer_key)
WHERE od.is_delivered
  AND dc.customer_state NOT IN ('unknown', 'Unknown')
GROUP BY dc.customer_state
HAVING delivered_orders >= 100
ORDER BY avg_days_late DESC;
