import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ["DATABASE_URL"]

QUERIES = {
    "schema": """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'orders_raw'
        ORDER BY ordinal_position;
    """,
    "row count": "SELECT COUNT(*) FROM orders_raw;",
    "sample rows": "SELECT * FROM orders_raw LIMIT 5;",
    "distinct currencies": "SELECT DISTINCT currency FROM orders_raw;",
    "distinct categories": "SELECT DISTINCT category FROM orders_raw;",
    "distinct status": "SELECT DISTINCT status FROM orders_raw;",
    "distinct channel": "SELECT DISTINCT channel FROM orders_raw;",
    "distinct country": "SELECT DISTINCT country FROM orders_raw;",
    "null counts": """
        SELECT
          COUNT(*) FILTER (WHERE order_id IS NULL) AS null_order_id,
          COUNT(*) FILTER (WHERE customer_id IS NULL) AS null_customer_id,
          COUNT(*) FILTER (WHERE qty IS NULL) AS null_qty,
          COUNT(*) FILTER (WHERE unit_price IS NULL) AS null_price,
          COUNT(*) FILTER (WHERE currency IS NULL) AS null_currency,
          COUNT(*) FILTER (WHERE order_ts IS NULL) AS null_order_ts,
          COUNT(*) FILTER (WHERE fx_reference_date IS NULL) AS null_fx_date,
          COUNT(*) FILTER (WHERE category IS NULL) AS null_category
        FROM orders_raw;
    """,
    "non-numeric qty sample": "SELECT DISTINCT qty FROM orders_raw WHERE qty !~ '^-?[0-9]+$' LIMIT 10;",
    "non-numeric unit_price sample": "SELECT DISTINCT unit_price FROM orders_raw WHERE unit_price !~ '^-?[0-9]+(\\.[0-9]+)?$' LIMIT 10;",
    "negative or zero qty": "SELECT COUNT(*) FROM orders_raw WHERE qty ~ '^-?[0-9]+$' AND qty::int <= 0;",
    "negative or zero unit_price": "SELECT COUNT(*) FROM orders_raw WHERE unit_price ~ '^-?[0-9]+(\\.[0-9]+)?$' AND unit_price::float <= 0;",
    "order_ts non-ISO formats": "SELECT DISTINCT order_ts FROM orders_raw WHERE order_ts !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T' LIMIT 10;",
    "fx_reference_date malformed": "SELECT DISTINCT fx_reference_date FROM orders_raw WHERE fx_reference_date !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' LIMIT 10;",
    "fx_reference_date later than order_ts": """
        SELECT COUNT(*) FROM orders_raw
        WHERE order_ts ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T'
        AND fx_reference_date::date > order_ts::date;
    """,
    "status breakdown": "SELECT status, COUNT(*) FROM orders_raw GROUP BY status;",
    "category null count": "SELECT COUNT(*) FROM orders_raw WHERE category IS NULL;",
    "duplicate order_id+sku group count": """
        SELECT COUNT(*) FROM (
            SELECT order_id, sku FROM orders_raw
            GROUP BY order_id, sku
            HAVING COUNT(*) > 1
        ) sub;
    """,
    "duplicate order_id+sku sample": """
        SELECT order_id, sku, customer_id, order_ts, qty, unit_price, currency
        FROM orders_raw
        WHERE (order_id, sku) IN (
            SELECT order_id, sku FROM orders_raw
            GROUP BY order_id, sku
            HAVING COUNT(*) > 1
        )
        ORDER BY order_id, sku
        LIMIT 20;
    """,
    "exact full-row duplicates": """
        SELECT order_id, sku, customer_id, order_ts, qty, unit_price, currency, COUNT(*)
        FROM orders_raw
        GROUP BY order_id, sku, customer_id, order_ts, qty, unit_price, currency
        HAVING COUNT(*) > 1
        LIMIT 10;
    """,
}


def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    for label, query in QUERIES.items():
        print(f"\n--- {label} ---")
        cur.execute(query)
        rows = cur.fetchall()
        if not rows:
            print("(no rows)")
        for row in rows:
            print(row)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()