import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ["DATABASE_URL"]


def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    print("--- fx_reference_date range ---")
    cur.execute("""
        SELECT MIN(fx_reference_date), MAX(fx_reference_date),
               COUNT(DISTINCT fx_reference_date) AS distinct_dates,
               COUNT(*) FILTER (WHERE fx_reference_date > CURRENT_DATE) AS future_dates
        FROM orders_clean;
    """)
    print(cur.fetchone())

    print("\n--- distinct currencies in orders_clean ---")
    cur.execute("SELECT DISTINCT currency FROM orders_clean;")
    print(cur.fetchall())

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()