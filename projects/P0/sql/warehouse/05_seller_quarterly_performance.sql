-- Count completed delivered items in each delivery quarter.
-- These observations determine the following quarter's simulated seller tier.
CREATE OR REPLACE TABLE `${PROJECT}.${WAREHOUSE}.seller_quarterly_performance` AS
-- This policy counts delivered items, not distinct orders.
SELECT i.seller_id, DATE_TRUNC(o.delivered_date, QUARTER) AS performance_quarter,
       COUNT(*) AS delivered_items,
       COUNTIF(o.delivered_date > o.estimated_delivery_date) AS late_items,
       SAFE_DIVIDE(COUNTIF(o.delivered_date > o.estimated_delivery_date), COUNT(*)) AS late_rate
FROM `${PROJECT}.${STAGING}.order_items` AS i
JOIN `${PROJECT}.${WAREHOUSE}.prepared_orders` AS o USING (order_id)
WHERE o.is_delivered
GROUP BY i.seller_id, performance_quarter;
