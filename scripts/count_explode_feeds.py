#!/usr/bin/env python3
"""Count exploded feed rows (ITA by priority, ESP all, non-ITA paid P1-4).

Run in Terminal.app with VPN (Cursor agent sandbox cannot use VPN DNS):

    cd ~/development/linkedin-wrapping
    set -a && source .env && set +a
    .venv/bin/python scripts/count_explode_feeds.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

root = Path(__file__).resolve().parent.parent
load_dotenv(root / ".env", override=True)

url = os.environ.get("JOB_FEED_SOURCE_DATABASE_URL")
if not url:
    sys.exit("JOB_FEED_SOURCE_DATABASE_URL missing")

# Optional: FORCE_RDS_HOST=192.168.163.188 if DNS fails in some environments
force_host = os.environ.get("FORCE_RDS_HOST")
if force_host:
    from sqlalchemy.engine.url import make_url

    url = str(make_url(url).set(host=force_host))

engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 20})

SQL_ITA = """
WITH ita_cities AS (
    SELECT jp.id AS job_posting_id, jt.ord AS city_ord, e.priority
    FROM job_postings.job_postings_1 jp
    JOIN employers.employers e ON e.id = jp.employers_id
    INNER JOIN JSON_TABLE(
        CASE WHEN JSON_VALID(jp.locations) THEN jp.locations ELSE '{"cities":[]}' END,
        '$.cities[*]'
        COLUMNS (ord FOR ORDINALITY, city_label VARCHAR(255) PATH '$.label', country_code VARCHAR(10) PATH '$.country_code')
    ) jt ON TRUE
    WHERE jt.country_code = 'ITA' AND NULLIF(TRIM(jt.city_label), '') IS NOT NULL
),
country_ita AS (
    SELECT DISTINCT jp.id AS job_posting_id
    FROM job_postings.job_postings_1 jp
    JOIN JSON_TABLE(
        CASE WHEN JSON_VALID(jp.locations) THEN jp.locations ELSE '{"countries":[]}' END,
        '$.countries[*]' COLUMNS (country_code VARCHAR(10) PATH '$.country_code')
    ) jt WHERE jt.country_code = 'ITA'
),
has_ita_city AS (SELECT DISTINCT job_posting_id FROM ita_cities),
ita_fallback AS (
    SELECT jp.id AS job_posting_id, 1 AS city_ord, e.priority
    FROM job_postings.job_postings_1 jp
    JOIN employers.employers e ON e.id = jp.employers_id
    JOIN country_ita ci ON ci.job_posting_id = jp.id
    LEFT JOIN has_ita_city hic ON hic.job_posting_id = jp.id
    WHERE hic.job_posting_id IS NULL
),
rows_ita AS (SELECT * FROM ita_cities UNION ALL SELECT * FROM ita_fallback)
SELECT priority, COUNT(*) AS exploded_rows, COUNT(DISTINCT job_posting_id) AS distinct_jobs
FROM rows_ita GROUP BY priority WITH ROLLUP ORDER BY priority IS NULL, priority
"""

SQL_ESP = """
WITH esp_cities AS (
    SELECT jp.id AS job_posting_id, jt.ord AS city_ord
    FROM job_postings.job_postings_1 jp
    INNER JOIN JSON_TABLE(
        CASE WHEN JSON_VALID(jp.locations) THEN jp.locations ELSE '{"cities":[]}' END,
        '$.cities[*]'
        COLUMNS (ord FOR ORDINALITY, city_label VARCHAR(255) PATH '$.label', country_code VARCHAR(10) PATH '$.country_code')
    ) jt ON TRUE
    WHERE jt.country_code = 'ESP' AND NULLIF(TRIM(jt.city_label), '') IS NOT NULL
),
country_esp AS (
    SELECT DISTINCT jp.id AS job_posting_id
    FROM job_postings.job_postings_1 jp
    JOIN JSON_TABLE(
        CASE WHEN JSON_VALID(jp.locations) THEN jp.locations ELSE '{"countries":[]}' END,
        '$.countries[*]' COLUMNS (country_code VARCHAR(10) PATH '$.country_code')
    ) jt WHERE jt.country_code = 'ESP'
),
has_esp_city AS (SELECT DISTINCT job_posting_id FROM esp_cities),
esp_fallback AS (
    SELECT jp.id AS job_posting_id, 1 AS city_ord
    FROM job_postings.job_postings_1 jp
    JOIN country_esp ce ON ce.job_posting_id = jp.id
    LEFT JOIN has_esp_city hec ON hec.job_posting_id = jp.id
    WHERE hec.job_posting_id IS NULL
),
rows_esp AS (SELECT * FROM esp_cities UNION ALL SELECT * FROM esp_fallback)
SELECT COUNT(*) AS exploded_rows, COUNT(DISTINCT job_posting_id) AS distinct_jobs FROM rows_esp
"""

SQL_OTHER = """
WITH all_cities AS (
    SELECT jp.id AS job_posting_id, jt.ord AS city_ord, jt.country_code
    FROM job_postings.job_postings_1 jp
    JOIN employers.employers e ON e.id = jp.employers_id
    INNER JOIN JSON_TABLE(
        CASE WHEN JSON_VALID(jp.locations) THEN jp.locations ELSE '{"cities":[]}' END,
        '$.cities[*]'
        COLUMNS (ord FOR ORDINALITY, city_label VARCHAR(255) PATH '$.label', country_code VARCHAR(10) PATH '$.country_code')
    ) jt ON TRUE
    WHERE jt.country_code IS NOT NULL AND jt.country_code <> 'ITA'
      AND NULLIF(TRIM(jt.city_label), '') IS NOT NULL
      AND e.product IN ('one', 'pro', 'pro_unlimited') AND e.priority IN (1, 2, 3, 4)
),
country_non_ita AS (
    SELECT DISTINCT jp.id AS job_posting_id, jt.country_code
    FROM job_postings.job_postings_1 jp
    JOIN employers.employers e ON e.id = jp.employers_id
    JOIN JSON_TABLE(
        CASE WHEN JSON_VALID(jp.locations) THEN jp.locations ELSE '{"countries":[]}' END,
        '$.countries[*]' COLUMNS (country_code VARCHAR(10) PATH '$.country_code')
    ) jt
    WHERE jt.country_code IS NOT NULL AND jt.country_code <> 'ITA'
      AND e.product IN ('one', 'pro', 'pro_unlimited') AND e.priority IN (1, 2, 3, 4)
),
has_city AS (SELECT DISTINCT job_posting_id, country_code FROM all_cities),
fallback AS (
    SELECT c.job_posting_id, 1 AS city_ord, c.country_code
    FROM country_non_ita c
    LEFT JOIN has_city hc ON hc.job_posting_id = c.job_posting_id AND hc.country_code = c.country_code
    WHERE hc.job_posting_id IS NULL
),
rows_other AS (SELECT * FROM all_cities UNION ALL SELECT * FROM fallback)
SELECT country_code, COUNT(*) AS exploded_rows, COUNT(DISTINCT job_posting_id) AS distinct_jobs
FROM rows_other GROUP BY country_code WITH ROLLUP
ORDER BY country_code IS NULL, exploded_rows DESC
"""


def main() -> None:
    with engine.connect() as conn:
        print("=== ITA any product, explode, by priority ===")
        for r in conn.execute(text(SQL_ITA)):
            print(dict(r._mapping))
        print("\n=== ESP any product/priority, explode ===")
        for r in conn.execute(text(SQL_ESP)):
            print(dict(r._mapping))
        print("\n=== Non-ITA product one/pro/pro_unlimited priority 1-4, explode ===")
        for r in conn.execute(text(SQL_OTHER)):
            print(dict(r._mapping))


if __name__ == "__main__":
    main()
