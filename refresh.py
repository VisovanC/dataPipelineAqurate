import os
import traceback
from datetime import datetime, timezone

import psycopg2
from dotenv import load_dotenv

import fx
import spend
import country

load_dotenv()
DB_URL = os.environ["DATABASE_URL"]


def log_run(status, detail=""):
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id SERIAL PRIMARY KEY,
            run_at TIMESTAMPTZ NOT NULL,
            status TEXT NOT NULL,
            detail TEXT
        );
    """)
    cur.execute(
        "INSERT INTO pipeline_runs (run_at, status, detail) VALUES (%s, %s, %s);",
        (datetime.now(timezone.utc), status, detail),
    )
    conn.commit()
    cur.close()
    conn.close()


def main():
    try:
        print("=== Refreshing FX rates ===")
        fx.main()

        print("\n=== Rebuilding customer_spend_eur ===")
        spend.main()

        print("\n=== Rebuilding country_category_revenue ===")
        country.main()

        log_run("success")
        print("\nDaily refresh completed successfully.")

    except Exception as e:
        error_detail = f"{type(e).__name__}: {e}"
        log_run("failure", error_detail)
        print(f"\nDaily refresh FAILED: {error_detail}")
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()