-- Keep one dimension row per product, including products with unknown categories.
CREATE OR REPLACE TABLE `${PROJECT}.${WAREHOUSE}.dim_product` AS
SELECT TO_HEX(SHA256(CONCAT('product|', p.product_id))) AS product_key,
       p.product_id,
       COALESCE(p.product_category_name, 'unknown') AS category_original,
       COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS category_en,
       p.product_weight_g AS weight_g, p.product_photos_qty AS photos_qty,
       p.product_length_cm AS length_cm, p.product_height_cm AS height_cm,
       p.product_width_cm AS width_cm,
       p.product_category_name IS NOT NULL AND t.product_category_name_english IS NULL AS translation_missing
FROM `${PROJECT}.${STAGING}.products` AS p
LEFT JOIN `${PROJECT}.${STAGING}.category_translation` AS t USING (product_category_name)
UNION ALL
SELECT 'unknown', CAST(NULL AS STRING), 'unknown', 'unknown',
       CAST(NULL AS INT64), CAST(NULL AS INT64), CAST(NULL AS INT64),
       CAST(NULL AS INT64), CAST(NULL AS INT64), FALSE;
