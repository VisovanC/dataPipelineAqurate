import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ["DATABASE_URL"]

CREATE_COUNTRY_CATEGORY_REVENUE = """
    DROP TABLE IF EXISTS country_category_revenue;

    CREATE TABLE country_category_revenue AS
    WITH converted AS (
      SELECT
        oc.country,
        oc.category,
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
      country,
      ROUND(SUM(line_total_eur), 2) AS total_revenue_eur
    FROM converted
    WHERE status = 'completed'
      AND category IN ('Books', 'Electronics')
    GROUP BY country
    HAVING SUM(line_total_eur) > 40000
    ORDER BY total_revenue_eur DESC;
"""


def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    print("Building country_category_revenue...")
    cur.execute(CREATE_COUNTRY_CATEGORY_REVENUE)
    conn.commit()

    cur.execute("SELECT * FROM country_category_revenue;")
    rows = cur.fetchall()
    print(f"\n{len(rows)} countries above the EUR 40,000 threshold:")
    for row in rows:
        print(row)
    print("\nAll countries (Books/Electronics revenue), for reference:")
    cur.execute("""
        SELECT
          oc.country,
          ROUND(SUM(
            CASE WHEN oc.currency = 'EUR' THEN oc.line_total
                 ELSE oc.line_total / fx.rate_to_eur END
          ), 2) AS total_revenue_eur
        FROM orders_clean oc
        LEFT JOIN LATERAL (
          SELECT rate_to_eur
          FROM fx_rates
          WHERE fx_rates.currency = oc.currency
            AND fx_rates.rate_date <= oc.fx_reference_date
          ORDER BY fx_rates.rate_date DESC
          LIMIT 1
        ) fx ON oc.currency != 'EUR'
        WHERE oc.status = 'completed'
          AND oc.category IN ('Books', 'Electronics')
        GROUP BY oc.country
        ORDER BY total_revenue_eur DESC;
    """)
    for row in cur.fetchall():
        print(row)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()