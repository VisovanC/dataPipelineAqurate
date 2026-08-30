# Writeup

## Data issues found in `orders_raw`

`orders_raw` came in with every column as text, on purpose — casting and validation happened later, so a malformed value couldn't break ingestion. Exploration showed the following issues:
 
- **Mixed timestamp formats** — `order_ts` came in three different formats: ISO 8601 (`2026-01-12T10:58:06`), `DD/MM/YYYY HH:MM` (`02/04/2026 10:50`), and Unix timestamps in seconds (`1781474381`). Normalized all three to a single `timestamp` type with a `CASE` statement matched by regex, rather than dropping the non-ISO rows, there's no reason to lose valid orders just because the source system logged dates inconsistently.
- **Invalid quantities and prices** — 167 rows had `qty` ≤ 0, and 24 rows had `unit_price` ≤ 0. Neither represents a real purchase, so both were dropped from `orders_clean`.
- **Sentinel price value (999999)** — 13 rows had `unit_price` set to exactly `999999`, spanning unrelated products. Since the value was identical across completely different products, it wasn't a real price mixup but a placeholder/error code from the source, I treated it the same as an invalid price and dropped it.
- **Exact full-row duplicates** — 183 groups (366 rows) were exact duplicates of `order_id` + `sku` + every other field. Confirmed they weren't legitimate multi-line orders before deduplicating with `DISTINCT`.
- **Test/seed data** — `status` included a `'test'` value on 101 rows, alongside the legitimate `'completed'` and `'refunded'` statuses. Dropped these entirely, they're not real orders.
- **Null `customer_id`** — 103 rows had no customer attached, meaning spend can't be attributed to anyone. Rather than deleting these rows outright, I kept them in `orders_clean` and excluded them only from the customer-spend aggregation in step 4, the order itself is still a real record worth keeping for auditability.
- **Null `category`** — 79 rows had no category. Filled as `'Unknown'` instead of dropping, since it doesn't affect the country/category breakdown and there's no reason to lose the row elsewhere.
- **Refunded orders** — 403 rows had `status = 'refunded'`. Kept in `orders_clean` as real records, but excluded from both the customer-spend and country-revenue totals, a refund shouldn't count as spend or revenue.

The general principle I followed: drop rows only when the data itself is invalid (bad quantities/prices, test records, duplicates). When the data is valid but simply shouldn't count toward a particular aggregation (refunds, unattributed orders), keep the row and filter it out downstream instead, so nothing gets silently lost from the underlying table.

## How I'd monitor this in production

- **`pipeline_runs` log table** — every run of `refresh.py` writes a row with a timestamp and a status (`success` or `failure`, with the error detail if it failed). If the daily job silently stopped running altogether, this table would simply stop getting new rows. Checking `MAX(run_at)` against the current date is an immediate way to spot a job that's gone quiet, which a plain crash-only alert wouldn't catch.
- **GitHub Actions failure notifications** — if the scheduled workflow itself fails (e.g. the FX API is down, or the DB connection fails), GitHub automatically emails the repo owner. This covers the loud-failure case without any extra setup.
- **Row-count sanity checks** — the more dangerous failure mode is the job running "successfully" but producing something obviously wrong, like `customer_spend_eur` coming back empty or with a fraction of the expected customers, without throwing an exception. In a real production version, I'd extend `refresh.py` to compare each day's row counts against the previous run and log a warning or even fail the run deliberately if a table came back suspiciously small. I didn't build this out for the exercise since the underlying `orders_raw` data is static, so row counts shouldn't change day to day here, but it's the first thing I'd add for a real, changing dataset.
- **FX rate gaps** — since FX conversion relies on backward-filling from the most recent available rate, a specific silent-failure risk is the FX source going stale (e.g. frankfurter.dev not publishing a new rate for several days). I'd monitor the max `rate_date` in `fx_rates` similarly to the pipeline run check — if it falls too far behind the current date, that's a sign the FX ingestion step is quietly failing even if the rest of the pipeline reports success.

## AI Usage: Tools; Kept vs. Changed

Used Claude throughout as a pair-programming partner, planning each step before writing code, drafting scripts, debugging errors as they came up, and helping structure this documentation.
 
- **What I kept largely as-is:**
  - The `LATERAL` join pattern for FX rate matching (backward-filling to the most recent available rate on or before `fx_reference_date`) — this was the correct approach for handling both weekend gaps and the intentionally future-dated rows, and I didn't have a reason to do it differently.
  - The overall table structure and script layout (`ingest.py` → `investigation.py` → `clean.py` → `fx.py` → `spend.py` → `country_category.py` → `refresh.py`) — kept each step as its own script rather than one large file, which made debugging and rerunning individual steps much easier.
  - Loading `orders_raw` entirely as `TEXT` at ingest, deferring type casting to the clean step.
- **What I changed or pushed back on:**
  - Chose a GitHub Actions scheduled workflow over Supabase's `pg_cron` for automation, since the repo was already set up and it avoided extra Supabase configuration.
  - Caught that the first version of `customer_spend_eur` returned unrounded EUR totals, asked for the `ROUND(..., 2)` fix once I noticed it in the output, since real currency shouldn't display that way.
  - Verified the FX conversion direction manually against a real order rather than just trusting it, since getting that backwards would have silently produced wrong totals everywhere downstream.
- **What was fully my own judgment call:**
  - Deciding refunded orders and rows with missing `customer_id`/`category` should be *kept* in `orders_clean` but excluded only from downstream aggregations, rather than deleted outright — wanted the pipeline to stay auditable.
  - Deciding the `999999` unit price was a sentinel/placeholder value rather than a real price, based on it appearing identically across unrelated products.
  - Deciding the `'test'` status rows and exact duplicate rows should be dropped entirely, since neither represents a real order.