-- Q1a: Which seller-to-customer state corridors have the highest late-delivery rates?
-- Corridors with fewer than 30 delivered items are excluded to remove small-volume noise.
-- Join uses seller_key (not seller_id) so each item is bound to the tier version valid
-- at purchase date; using seller_id alone would multiply rows across all history versions.
SELECT
  ds.seller_state,
  dc.customer_state,
  COUNT(*)                                                  AS delivered_items,
  COUNTIF(f.is_late)                                        AS late_items,
  ROUND(SAFE_DIVIDE(COUNTIF(f.is_late), COUNT(*)), 4)       AS late_rate
FROM `${PROJECT}.${WAREHOUSE}.fact_order_item` AS f
JOIN `${PROJECT}.${WAREHOUSE}.dim_seller`   AS ds USING (seller_key)
JOIN `${PROJECT}.${WAREHOUSE}.dim_customer` AS dc USING (customer_key)
WHERE f.is_delivered
  AND ds.seller_state   NOT IN ('unknown', 'Unknown')
  AND dc.customer_state NOT IN ('unknown', 'Unknown')
GROUP BY ds.seller_state, dc.customer_state
HAVING delivered_items >= 30
ORDER BY late_rate DESC
LIMIT 20;
