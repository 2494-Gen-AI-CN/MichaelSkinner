-- Q1b: Which product categories have the highest late-delivery rates?
-- Use item-weighted rates to identify categories for delivery-quality review.
-- Categories with fewer than 50 delivered items are excluded to reduce small-volume noise.
-- Known products without a category remain labelled unknown. Only the separate
-- unknown product-reference member is excluded, not the unknown-category group.
SELECT
  COALESCE(dp.category_en, 'unknown')                       AS category,
  COUNT(*)                                                  AS delivered_items,
  COUNTIF(f.is_late)                                        AS late_items,
  ROUND(SAFE_DIVIDE(COUNTIF(f.is_late), COUNT(*)), 4)       AS late_rate
FROM `${PROJECT}.${WAREHOUSE}.fact_order_item` AS f
JOIN `${PROJECT}.${WAREHOUSE}.dim_product` AS dp USING (product_key)
WHERE f.is_delivered
  AND dp.product_key != 'unknown'
GROUP BY category
HAVING delivered_items >= 50
ORDER BY late_rate DESC
LIMIT 20;
