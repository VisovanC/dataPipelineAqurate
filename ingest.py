import requests
import psycopg2
import psycopg2.extras
import json
import os
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ["DATABASE_URL"]

SOURCE_URL = "https://jzozteoirwfczccltcdr.supabase.co/rest/v1/orders_raw"
API_KEY = "sb_publishable_Xwjiw--qkKcbMuSbKd6I2w_wN9mpNTv"

HEADERS = {
    "apikey": API_KEY,
    "Authorization": f"Bearer {API_KEY}",
}

def fetch_all_rows(page_size=1000):
    all_rows = []
    offset = 0
    while True:
        headers = {**HEADERS, "Range-Unit": "items", "Range": f"{offset}-{offset + page_size - 1}"}
        resp = requests.get(SOURCE_URL, headers=headers)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return all_rows

def main():
    rows = fetch_all_rows()
    print(f"Fetched {len(rows)} rows")
    with open("orders_raw_snapshot.json", "w") as f:
        json.dump(rows, f)

    if not rows:
        print("No rows fetched — aborting")
        return
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    columns = list(rows[0].keys())
    col_list = ", ".join(columns)
    col_types = ", ".join(f"{c} TEXT" for c in columns)

    cur.execute(f"DROP TABLE IF EXISTS orders_raw;")
    cur.execute(f"CREATE TABLE orders_raw ({col_types});")

    values = [[row.get(c) for c in columns] for row in rows]
    psycopg2.extras.execute_values(
        cur, f"INSERT INTO orders_raw ({col_list}) VALUES %s", values
    )
    conn.commit()
    cur.close()
    conn.close()
    print("Loaded into orders_raw")

if __name__ == "__main__":
    main()