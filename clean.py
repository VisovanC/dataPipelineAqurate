import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ["DATABASE_URL"]

CREATE_ORDERS_CLEAN = """
    DROP TABLE IF EXISTS orders_clean;

    CREATE TABLE orders_clean AS
    WITH parsed AS (
      SELECT DISTINCT
        order_id,
        NULLIF(customer_id, '') AS customer_id,
        customer_email,
        CASE
          WHEN order_ts ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T' THEN order_ts::timestamp
          WHEN order_ts ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4} [0-9]{2}:[0-9]{2}$'
            THEN to_timestamp(order_ts, 'DD/MM/YYYY HH24:MI')
          WHEN order_ts ~ '^[0-9]+$' THEN to_timestamp(order_ts::bigint)
          ELSE NULL
        END AS order_ts,
        status,
        channel,
        sku,
        product_name,
        COALESCE(category, 'Unknown') AS category,
        qty::int AS qty,
        unit_price::numeric AS unit_price,
        currency,
        country,
        fx_reference_date::date AS fx_reference_date
      FROM orders_raw
    )
    SELECT *,
      qty * unit_price AS line_total
    FROM parsed
    WHERE status != 'test'
      AND qty > 0
      AND unit_price > 0
      AND unit_price != 999999
      AND order_ts IS NOT NULL;
"""


def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    print("Building orders_clean...")
    cur.execute(CREATE_ORDERS_CLEAN)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM orders_raw;")
    raw_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM orders_clean;")
    clean_count = cur.fetchone()[0]

    print(f"orders_raw:   {raw_count} rows")
    print(f"orders_clean: {clean_count} rows")
    print(f"Dropped:      {raw_count - clean_count} rows")

    cur.execute("SELECT COUNT(*) FROM orders_clean WHERE customer_id IS NULL;")
    print(f"  - rows with NULL customer_id (kept, excluded downstream): {cur.fetchone()[0]}")

    cur.execute("SELECT COUNT(*) FROM orders_clean WHERE status = 'refunded';")
    print(f"  - refunded rows (kept, excluded downstream): {cur.fetchone()[0]}")

    cur.execute("SELECT COUNT(*) FROM orders_clean WHERE category = 'Unknown';")
    print(f"  - rows with category filled as 'Unknown': {cur.fetchone()[0]}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()