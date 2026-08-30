import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ["DATABASE_URL"]

CREATE_CUSTOMER_SPEND_EUR = """
    DROP TABLE IF EXISTS customer_spend_eur;

    CREATE TABLE customer_spend_eur AS
    WITH converted AS (
      SELECT
        oc.order_id,
        oc.customer_id,
        oc.status,
        CASE
          WHEN oc.currency = 'EUR' THEN oc.line_total
          ELSE oc.line_total / fx.rate_to_eur
        END AS line_total_eur
      FROM orders_clean oc
      LEFT JOIN LATERAL (
        SELECT rate_to_eur
        FROM fx_rates
        WHERE fx_rates.currency = oc.currency
          AND fx_rates.rate_date <= oc.fx_reference_date
        ORDER BY fx_rates.rate_date DESC
        LIMIT 1
      ) fx ON oc.currency != 'EUR'
    )
    SELECT
        customer_id,
        ROUND(SUM(line_total_eur), 2) AS total_spend_eur
    FROM converted
    WHERE customer_id IS NOT NULL
        AND status = 'completed'
    GROUP BY customer_id
    ORDER BY total_spend_eur DESC;
    """


def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    print("Building customer_spend_eur...")
    cur.execute(CREATE_CUSTOMER_SPEND_EUR)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM customer_spend_eur;")
    print(f"customer_spend_eur: {cur.fetchone()[0]} customers")

    cur.execute("""
        SELECT COUNT(*) FROM orders_clean
        WHERE currency != 'EUR'
    """)
    print(f"  RON line items converted: {cur.fetchone()[0]}")

    print("\nTop 10 customers by spend:")
    cur.execute("SELECT * FROM customer_spend_eur LIMIT 10;")
    for row in cur.fetchall():
        print(row)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()