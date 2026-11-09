# Beyond the Delivery Date

## Business case

Our client is the Head of Marketplace Operations at a Brazilian online marketplace. They want to understand where delivery promises break, how lateness relates to customer reviews, and which sellers or regions need attention. We use Olist's historical orders to build a BigQuery warehouse for those questions.

1. Which seller-to-customer state corridors and product categories have the highest late-delivery rates?
2. How do review scores differ between early, on-time, and late deliveries?
3. Are delivery promises too optimistic in some customer regions?
4. How does freight charged relative to item price relate to satisfaction?
5. How do seller outcomes compare across periods under a simulated quarterly watchlist policy?

**Team:** Michael Skinner and Sukhman Brar (https://github.com/2494-Gen-AI-CN/SukhmanBrar).

The setup, ingestion, cleaning, and warehouse build are complete. SQL analysis, correlation, charts, recommendations, and the presentation are still to be added. The schema diagram will be drawn separately.

## Dataset

[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce), licensed CC BY-NC-SA 4.0 and used for non-commercial education with attribution to Olist. The data covers 2016–2018.

We use eight CSVs: orders, order items, products, customers, sellers, payments, reviews, and category translation. Geolocation is excluded because our questions use states rather than coordinates. Download the dataset from Kaggle and unzip it into `data/raw/`.

The source files contain 99,441 orders and 112,650 items. Eight orders are marked delivered but have no customer delivery date, so they are rejected. Their eight items are retained in the warehouse with `order_missing = TRUE` and unknown order outcomes.

## How it works

```text
CSV files -> pandas cleaning -> p0_staging -> warehouse SQL -> p0_warehouse
                                  |                              |
                            rejects + load_log              analysis and charts
                                                            (to be added)
```

The Python job reads the file paths, schemas, keys, and rules from YAML. It validates each file, separates rejected rows, removes duplicates, loads clean data to staging, and records the result. A source error is logged and the remaining sources continue.

Warehouse SQL then creates the dimensions and fact table directly from staging. There is no intermediate database.

## Run the project

Tested with Python 3.14. Use Python 3.11 or newer and install the Google Cloud CLI for `gcloud` and `bq`.

```bash
git clone https://github.com/2494-Gen-AI-CN/MichaelSkinner.git
cd MichaelSkinner/projects/P0
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cp config/config.example.yaml config/config.yaml
```

Set `GCP_PROJECT` in `.env` to your Google Cloud project ID. Our project is `olist-delivery-insights`. The Python commands read `.env`; terminal commands need the exported variable below.

```bash
export GCP_PROJECT="your-project-id"
gcloud auth login
gcloud config set project "$GCP_PROJECT"
gcloud auth application-default login
bq --project_id="$GCP_PROJECT" query --use_legacy_sql=false 'SELECT 1 AS ok'
```

The terminal login and Python login are separate. Credentials stay outside this repository. If using a service-account file instead, keep it outside the repository and set `GOOGLE_APPLICATION_CREDENTIALS` to its path.

Create the datasets once in the same location:

```bash
bq --project_id="$GCP_PROJECT" --location=US mk --dataset "${GCP_PROJECT}:p0_staging"
bq --project_id="$GCP_PROJECT" --location=US mk --dataset "${GCP_PROJECT}:p0_warehouse"
```

If they already exist, keep them. A BigQuery sandbox is sufficient; billing is not needed.

```bash
# Validate the CSVs locally without uploading.
python -m src.ingest.main --config config/config.yaml --dry-run

# Load staging, then build the warehouse.
python -m src.ingest.main --config config/config.yaml
python -m src.build_warehouse --config config/config.yaml

# Run unit tests without connecting to BigQuery.
python -m pytest -q
```

Ingestion saves local logs and rejects in `data/runs/`. The warehouse builder saves check results in `data/warehouse_checks.csv`. To open the warehouse SQL in the BigQuery console, render its project/dataset placeholders first:

```bash
python -m src.build_warehouse --config config/config.yaml --render-only
```

The runnable copies are saved in `data/rendered_sql/`. Run them in filename order.

## Cleaning rules

| Check | Action |
| --- | --- |
| Missing expected column | Fail that source and keep its previous staging table |
| Missing key or required field | Reject the row |
| Invalid numeric or date text | Reject the row |
| Item price / freight | Require positive price and nonnegative freight |
| Review score | Require a whole number from 1 to 5 |
| Order status | Require a known status listed in the config |
| Delivered order | Require a customer delivery date on or after purchase |
| Estimated delivery date | Must not precede purchase |
| Exact duplicate after cleaning | Keep one and count removed copies |
| Same source key, different values | Reject the conflicting versions |
| Missing optional fields | Keep null values, including undelivered order dates and product measurements |

Strings are trimmed, and state/status text is normalized where configured. Identifiers and ZIP prefixes remain strings. Money is loaded as BigQuery NUMERIC. Source dates have no timezone, so they are stored as DATETIME.

Each reject contains the original record and its first failure reason. Review IDs are not unique across orders, so their key is `(review_id, order_id)`. Adding a source using the supported rules requires a new configuration entry rather than a new ingestion function.

## Reruns and logs

Each source replaces its staging table instead of appending duplicate data. A fingerprint identifies its file contents and cleaning settings. If it matches the last successful load and the table still has the same version and row count, that source is skipped. Missing or expired tables are loaded again. Use `--force` to reload unchanged sources.

When changing cleaning behavior, increase `CLEANING_VERSION` in `src/ingest/config.py` so the sources are reprocessed. Run ingestion and the warehouse build one at a time, with the warehouse build after ingestion.

`load_log` records one row per source per run: run ID, source, start/end time, status, file hash, rows read, rows loaded, rows rejected, duplicates removed, and errors. Audit records are appended using batch jobs. Retries or forced loads can add reject-history entries, so inspect them by run ID.

[Sample load log](docs/sample_load_log.csv) and [sample rejects](docs/sample_rejects.csv) come from the initial verified BigQuery load. That load accepted **550,751 source records**, rejected **8 orders**, and removed **0 duplicates**. An unchanged second run loaded zero additional records.

## Warehouse

The fact grain is **one row per `(order_id, order_item_id)`**.

| Table | Grain | Verified rows |
| --- | --- | ---: |
| `fact_order_item` | Order item | 112,650 |
| `dim_product` | Product, plus unknown | 32,952 |
| `dim_customer` | Customer record, plus unknown | 99,442 |
| `dim_seller` | Seller history version, plus unknown | 3,322 |
| `dim_date` | Calendar date, plus unknown | 801 |

`prepared_orders` sums payments and selects the latest review before joining to items. `order_delivery` contains one row per known order with items: **98,658 rows**. The 775 accepted orders without items remain in `prepared_orders` but do not enter the item fact.

Products with missing categories are labelled `unknown` (610 products). Thirteen products have categories without an English translation; the original label is kept. Each dimension also has an unknown row for missing references.

See the [data dictionary](docs/data_dictionary.md) for field definitions and join keys.

### Seller history

The type 2 seller dimension uses a simulated policy: a seller is Watchlist in a quarter if the previous delivery quarter had at least **20 delivered items** and a late rate of at least **15%**. Otherwise the label is Standard, including quarters with insufficient data.

A change closes the old version and opens a new one. Join dates follow `effective_from <= purchase_date < effective_to`. The latest version has `effective_to = 9999-12-31` and `is_current = TRUE`. The fact already stores the seller version valid on its purchase date.

The SQL uses `LAG` to compare a tier with its previous value and `LEAD` to close a version at the next change. The verified history has **113 sellers with tier changes** and **226 transitions**. This is a project-defined policy, not an observed Olist intervention or evidence of a causal effect. Current means latest in the historical data, not performance today.

### Engineered features

| Feature | Rule |
| --- | --- |
| `is_late` | Delivered calendar date is after the promised date |
| `days_late` | Delivered date minus promised date; negative means early |
| `lateness_bucket` | Early, on time, 1–3, 4–7, or 8+ days late |
| `freight_ratio` | Item freight charge divided by item price |
| `promise_days` | Promised date minus purchase date |
| `delivery_days` | Delivered date minus purchase date |

Delivery outcomes stay null for undelivered or unknown orders. The build checks validate row counts, unique keys, dimension links, and seller history intervals.

## Partner access to the shared warehouse

To use the existing tables, the project owner can open Google Cloud's IAM page for `olist-delivery-insights`, choose **Grant access**, enter the partner's Google account email, and add these two project roles:

- **BigQuery Data Viewer** (`roles/bigquery.dataViewer`): read the staging and warehouse tables and views.
- **BigQuery Job User** (`roles/bigquery.jobUser`): run queries in this project.

These project-level roles cover both datasets, including staging tables used by warehouse views. See [Google's role reference](https://cloud.google.com/bigquery/docs/access-control). The partner uses their own Google login and does not need a copy of the owner's credentials.

After access is granted, the partner can open [the shared BigQuery project](https://console.cloud.google.com/bigquery?project=olist-delivery-insights) and run:

```sql
SELECT COUNT(*) AS item_count
FROM `olist-delivery-insights.p0_warehouse.fact_order_item`;
```

The expected count is **112650**. For Python access, complete `gcloud auth application-default login` with the invited account and set local `GCP_PROJECT=olist-delivery-insights`. The partner can query the existing tables without rerunning ingestion or the warehouse build.

## Remaining analysis

The next contribution will add at least five SQL files answering the business questions, a correlation with a non-causal explanation, at least three Matplotlib charts from BigQuery results, and a slide deck. One SQL file must use seller history. Findings, chart links, recommendations, and the teammate repository link should be added here once ready.

For the analysis:

- Join `fact_order_item` to dimensions using their surrogate keys. Joining to every seller version using only `seller_id` multiplies rows.
- Use `order_delivery` or a deduplicated order-level CTE for review averages, payment totals, and correlations. Order-level values repeat on item rows; `COUNT(DISTINCT order_id)` does not fix a separate repeated average or sum.
- Use `WHERE is_delivered` for delivery rates and state whether the denominator counts items or orders.
- Write the question and interpretation at the top of each analysis SQL file.

The data is historical, reviews are self-selected, and association does not establish cause. Freight charged is not shipping cost, and value on late orders is not lost revenue.

## Files

The ingestion code can be read in this order:

1. `main.py` loops through the sources and records each result.
2. `config.py` reads YAML and identifies changed inputs.
3. `clean.py` converts values, applies rules, and separates rejects.
4. `load.py` sends pandas tables to BigQuery.

```text
config/                  Source configuration
src/ingest/              Read, clean, load, and log
src/build_warehouse.py   Run warehouse SQL and checks
sql/warehouse/           Dimensions, fact, views, and validation
tests/                   Local pytest tests
docs/                    Field dictionary and required audit samples
data/                    Raw CSVs and generated local reports (ignored)
```

`.env`, local configuration, raw data, and generated reports are ignored by Git. BigQuery sandbox tables expire after 60 days, so expired tables need to be recreated by rerunning the jobs.
