# Step 1: Ingest

## Goal
Pull the `orders_raw` table from the provided Supabase REST endpoint and load it into a database I control, as raw as possible, without assuming anything about data quality yet.

## Setup
- Created a new Supabase project to act as my own database.
- Connected via the Session Pooler connection string.
- Used `psycopg2` for the Postgres connection and `python-dotenv` to load credentials.

## Ingestion approach (`ingest.py`)
- Fetched all rows from the source endpoint (`orders_raw`) via paginated `GET` requests using the `Range` header.
- Saved a local JSON snapshot of the raw API response (`orders_raw_snapshot.json`) before touching the database, as a reproducibility check.
- Loaded everything into a Postgres table (`orders_raw`) with **every column typed as `TEXT`**, not casting types at ingest time. Raw ingest should preserve the source data byte-for-byte where possible; type casting and validation happens later in the `orders_clean` step, so a malformed value doesn't break ingestion.

Result: **9,268 rows** loaded successfully.

## Schema discovered
```
order_id            text
customer_id         text
customer_email      text
order_ts            text
status               text
channel              text
sku                  text
product_name          text
category              text
qty                   text
unit_price            text
currency              text
country               text
fx_reference_date      text
```
Note: there is no single `amount` column — line-item total must be derived as `qty × unit_price`.

## Exploration process
- Checked row count to ensure that all data was ingested into the Supabase DB and looked at 5 sample rows - discovered duplicate values.
- Being that duplicates were discovered, I decided to look at all distinct values.
- Tested data quality (nulls, bad numeric formats, mixed date formats, duplicates), results can be seen below.

## Data issues found during exploration (informing the upcoming `orders_clean` step)

| Issue | Count | Notes |
|---|---|---|
| `customer_id` is NULL | 103 rows | Can't attribute spend to a customer |
| `category` is NULL | 79 rows | |
| `qty` ≤ 0 | 167 rows | Invalid — not a real purchase quantity |
| `unit_price` ≤ 0 | 24 rows | Invalid |
| `status = 'test'` | 101 rows | Looks like test data, not real orders |
| `status = 'refunded'` | 403 rows | Real record, but shouldn't count toward spend/revenue totals |
| `order_ts` mixed formats | — | Three formats found: ISO 8601 (`2026-01-12T10:58:06`), `DD/MM/YYYY HH:MM` (`02/04/2026 10:50`), and Unix timestamp in seconds (`1781474381`) |
| Exact full-row duplicates (`order_id` + `sku` + all other fields identical) | 183 groups (366 rows) | Confirmed via full-row comparison — safe to de-duplicate with `DISTINCT` |
| `fx_reference_date` later than `order_ts` | 5,592 rows (~60%) | Expected per the assignment spec — some FX reference dates are intentionally set in the future to simulate change. Doesn't affect cleaning, but is critical for the FX join logic in the customer-spend step |

Distinct values confirmed:
- `currency`: `RON`, `EUR`
- `category`: `Electronics`, `Sports`, `Home & Kitchen`, `Books`, `Fashion`, `Beauty`, and NULL
- `status`: `completed`, `refunded`, `test`
- `channel`: `marketplace`, `web`, `mobile_app`
- `country`: `RO`, `BG`, `DE`, `HU`

# Step 2: Clean
 
## Goal
Build `orders_clean` from `orders_raw`, resolving the issues found during exploration.
 
## Further investigation
- Checked for structural inconsistencies that a single-column `DISTINCT` wouldn't catch: whether `order_id` ever maps to more than one `customer_id`, whether `sku` ever maps to more than one `product_name`, and whitespace/casing issues in categorical fields. All came back clean.
- Checked `unit_price` and `qty` ranges for outliers. `qty` ranged -3 to 3 (already covered by the ≤0 rule). `unit_price` had a max of 999999 — pulled the affected rows and found the same value (`999999`) across 13 rows spanning unrelated products (a serum, an air fryer, a book, dumbbells). No real price signal, so treated as a sentinel/placeholder value rather than a genuine price.

## Cleaning decisions
 
| Issue | Count | Handling |
|---|---|---|
| `customer_id` is NULL | 103 rows | Kept in table, excluded from customer-spend aggregation downstream |
| `category` is NULL | 79 rows | Filled as `'Unknown'` |
| `qty` ≤ 0 | 167 rows | Dropped |
| `unit_price` ≤ 0 | 24 rows | Dropped |
| `unit_price = 999999` | 13 rows | Dropped — sentinel/placeholder value, not a real price |
| `status = 'test'` | 101 rows | Dropped |
| `status = 'refunded'` | 403 rows | Kept in table, excluded from revenue totals downstream |
| `order_ts` mixed formats | all rows | Normalized to a single timestamp type |
| Exact full-row duplicates | 183 groups (366 rows) | De-duplicated with `DISTINCT` |
 
`refunded` and NULL `customer_id`/`category` rows are kept in `orders_clean` rather than deleted — they're valid records, just excluded from spend/revenue totals in later steps. Keeps the table auditable.
 
## Result (`clean.py`)
```
orders_raw:   9268 rows
orders_clean: 8787 rows
Dropped:      481 rows
  - rows with NULL customer_id (kept, excluded downstream): 94
  - refunded rows (kept, excluded downstream): 398
  - rows with category filled as 'Unknown': 76
```
481 dropped is less than the sum of individual issue counts above (~671) because of overlap — e.g. a row can be both `status = 'test'` and have a bad price, counted once. Same reason the NULL customer_id, refunded, and Unknown counts shifted slightly from the raw numbers.

# Step 3: Exchange rates

## Goal
Pull daily FX rates and store them, so orders in RON can be converted to EUR.

## Investigation
- Checked the `fx_reference_date` range in `orders_clean` and the currencies actually present, before pulling anything: range was 2026-08-23 to 2026-09-03 (12 distinct dates), only RON and EUR present. 2,889 rows had a future `fx_reference_date`.
- Today is 2026-08-30, so dates from 2026-08-31 onward can't have a published rate yet — no FX source, real or free, can return a rate for a day that hasn't happened. Needed a fallback rule instead of just pulling exact-date matches.
- Decided to use the most recent available rate on or before `fx_reference_date` (backward-fill). Standard approach for FX gaps, the same logic markets already use for weekends/holidays when no rate is published that day.

## Ingestion (`fx.py`)
- Pulled RON rates (base=EUR) from frankfurter.dev for 2026-08-23 to 2026-08-30 (clamped to today, since nothing later exists yet).
- Got 6 days back instead of a full range — frankfurter doesn't publish weekend rates. 2026-08-23 snapped back to 2026-08-21 (last trading day), and 2026-08-29/30 are missing entirely, same reason. This is expected, not a bug — it's exactly the gap the backward-fill logic is meant to cover.
- Stored as `fx_rates(rate_date, currency, rate_to_eur)`, where `rate_to_eur` is RON-per-1-EUR.

## Rate-matching logic
Used a `LATERAL` join to pick, for each order, the closest `fx_rates` row on or before its `fx_reference_date`:
```sql
LEFT JOIN LATERAL (
  SELECT rate_date, rate_to_eur
  FROM fx_rates
  WHERE fx_rates.currency = oc.currency
    AND fx_rates.rate_date <= oc.fx_reference_date
  ORDER BY fx_rates.rate_date DESC
  LIMIT 1
) fx ON TRUE
```
Spot-checked against a sample of RON orders, weekend and future dates all correctly fell back to 2026-08-28 (last available rate), and orders with a `fx_reference_date` that was itself a trading day used that date's rate directly. Confirms the fallback logic is correct.

# Step 4: Customer spend in EUR

## Goal
Build a table of total amount spent by each customer in EUR, converting non-EUR orders using the FX logic from step 3.

## Conversion logic
- `rate_to_eur` is RON-per-1-EUR, so converting a RON amount to EUR means **dividing** by the rate, not multiplying.
- Excluded rows with NULL `customer_id` (can't attribute spend to a customer — 94 rows from step 2).
- Excluded `status = 'refunded'` (398 rows from step 2) — not real spend.
- Rounded the final EUR sum to 2 decimals — raw division produces long decimals, not how currency should be reported.

## Result (`spend.py`)
```
customer_spend_eur: 1867 customers
  RON line items converted: 1830

Top 10 customers by spend:
('1571', 2171.35)
('1714', 2048.19)
('1707', 1870.73)
('836', 1829.39)
('40', 1794.14)
('1434', 1769.55)
('578', 1754.07)
('620', 1748.31)
('1268', 1687.50)
('1289', 1681.87)
```