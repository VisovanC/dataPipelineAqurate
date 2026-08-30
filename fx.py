import os
import requests
import psycopg2
import psycopg2.extras
from datetime import date
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ["DATABASE_URL"]

START_DATE = "2026-08-23"
END_DATE = min(date.today().isoformat(), "2026-09-03")

BASE_CURRENCY = "EUR"
TARGET_CURRENCY = "RON"


def fetch_rates():
    url = f"https://api.frankfurter.dev/v1/{START_DATE}..{END_DATE}"
    params = {"base": BASE_CURRENCY, "symbols": TARGET_CURRENCY}
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    return data["rates"]


def main():
    rates = fetch_rates()
    print(f"Fetched {len(rates)} days of rates ({START_DATE} to {END_DATE})")

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS fx_rates;")
    cur.execute("""
        CREATE TABLE fx_rates (
            rate_date DATE NOT NULL,
            currency TEXT NOT NULL,
            rate_to_eur NUMERIC NOT NULL,
            PRIMARY KEY (rate_date, currency)
        );
    """)

    rows = [
        (rate_date, TARGET_CURRENCY, rate_value)
        for rate_date, currencies in rates.items()
        for rate_value in [currencies[TARGET_CURRENCY]]
    ]
    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO fx_rates (rate_date, currency, rate_to_eur) VALUES %s",
        rows,
    )
    conn.commit()

    cur.execute("SELECT * FROM fx_rates ORDER BY rate_date;")
    for row in cur.fetchall():
        print(row)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()