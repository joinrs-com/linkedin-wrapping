#!/usr/bin/env python3
"""Count exploded location rows per campaign bucket (VPN / production source).

    set -a && source .env && set +a
    .venv/bin/python scripts/count_feed_buckets.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "scripts"))
load_dotenv(root / ".env", override=True)

from feed_buckets import BUCKETS, bucket_for_country  # noqa: E402
from job_feed_common import apply_job_feed_db_qualifiers  # noqa: E402

SQL = apply_job_feed_db_qualifiers(
    """
WITH city_rows AS (
    SELECT
        jp.id AS job_posting_id,
        jt.country_code,
        TRIM(SUBSTRING_INDEX(jt.city_label, ' - ', 1)) AS loc_label
    FROM job_postings.job_postings_1 jp
    INNER JOIN JSON_TABLE(
        CASE WHEN JSON_VALID(jp.locations) THEN jp.locations ELSE '{"cities":[]}' END,
        '$.cities[*]'
        COLUMNS (
            city_label VARCHAR(255) PATH '$.label',
            country_code VARCHAR(10) PATH '$.country_code'
        )
    ) jt ON TRUE
    WHERE NULLIF(TRIM(jt.city_label), '') IS NOT NULL
      AND NULLIF(TRIM(jt.country_code), '') IS NOT NULL
),
country_only AS (
    SELECT
        jp.id AS job_posting_id,
        jt.country_code
    FROM job_postings.job_postings_1 jp
    INNER JOIN JSON_TABLE(
        CASE WHEN JSON_VALID(jp.locations) THEN jp.locations ELSE '{"countries":[]}' END,
        '$.countries[*]'
        COLUMNS (country_code VARCHAR(10) PATH '$.country_code')
    ) jt ON TRUE
    WHERE NULLIF(TRIM(jt.country_code), '') IS NOT NULL
),
has_city AS (
    SELECT DISTINCT job_posting_id, country_code FROM city_rows
),
country_fallback AS (
    SELECT co.job_posting_id, co.country_code, co.country_code AS loc_label
    FROM country_only co
    LEFT JOIN has_city hc
      ON hc.job_posting_id = co.job_posting_id AND hc.country_code = co.country_code
    WHERE hc.job_posting_id IS NULL
),
exploded AS (
    SELECT job_posting_id, country_code, loc_label FROM city_rows
    UNION ALL
    SELECT job_posting_id, country_code, loc_label FROM country_fallback
)
SELECT country_code, COUNT(*) AS rows_n, COUNT(DISTINCT job_posting_id) AS jobs_n
FROM exploded
GROUP BY country_code
ORDER BY rows_n DESC
"""
)


def main() -> None:
    url = os.environ.get("JOB_FEED_SOURCE_DATABASE_URL")
    if not url:
        raise SystemExit("JOB_FEED_SOURCE_DATABASE_URL required")
    eng = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 30})
    bucket_rows: dict[str, int] = {b: 0 for b in BUCKETS}
    bucket_jobs: dict[str, set[int]] = {b: set() for b in BUCKETS}
    total_rows = 0
    countries = 0
    with eng.connect() as conn:
        for country_code, rows_n, jobs_n in conn.execute(text(SQL)):
            countries += 1
            total_rows += int(rows_n)
            b = bucket_for_country(str(country_code) if country_code is not None else "")
            bucket_rows[b] += int(rows_n)
            print(f"  {country_code}: rows={rows_n} jobs={jobs_n} → {b}")
    print("---")
    print(f"countries={countries} explode_rows={total_rows}")
    for b in BUCKETS:
        print(f"bucket {b}: rows={bucket_rows[b]}")
    # sanity vs user baseline ~342780
    print(f"(baseline explode_rows≈342780)")


if __name__ == "__main__":
    main()
