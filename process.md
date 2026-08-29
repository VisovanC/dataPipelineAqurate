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
