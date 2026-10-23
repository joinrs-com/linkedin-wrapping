#!/usr/bin/env python3
"""Refresh Jooble/Adzuna/abroad descriptions (no intro + HTML) and regenerate gzip artifacts.

Safe to interrupt and re-run: already-updated descriptions are skipped (resume).

Run in Terminal.app with VPN (Cursor agent cannot use VPN DNS):

    cd ~/development/linkedin-wrapping
    set -a && source .env && set +a
    .venv/bin/python scripts/refresh_descriptions_and_artifacts.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "scripts"))
load_dotenv(project_root / ".env", override=True)

import improve_job_descriptions as ijd  # noqa: E402
from job_feed_common import create_mysql_engine, load_sql, sync_feed_table  # noqa: E402
from run_job_feed_pipeline import FEED_CONFIGS, _generate_feed_xml_artifacts  # noqa: E402


def main() -> None:
    if not os.getenv("DATABASE_URL") or not os.getenv("JOB_FEED_SOURCE_DATABASE_URL"):
        raise SystemExit("DATABASE_URL and JOB_FEED_SOURCE_DATABASE_URL required")

    src = create_mysql_engine(os.environ["JOB_FEED_SOURCE_DATABASE_URL"])
    dest = ijd.create_database_engine()

    for name in ("jooble", "adzuna", "jooble_abroad"):
        cfg = next(c for c in FEED_CONFIGS if c.name == name)
        print("=" * 60)
        print(f"Sync {name} (normalize_html={cfg.normalize_html}, refresh={cfg.refresh_descriptions})")
        sql = load_sql(project_root, cfg.sql_file)
        with src.connect() as sc, dest.connect() as dc:
            r = sync_feed_table(
                dc,
                sc,
                table=cfg.table,
                select_sql=sql,
                columns=cfg.columns,
                id_column=cfg.id_column,
                description_column=cfg.description_column,
                enriched={},
                string_id=cfg.string_id,
                normalize_html=cfg.normalize_html,
                refresh_descriptions=True,
            )
        print(
            f"  active={r.active} inserted={r.inserted} deleted={r.deleted} "
            f"unchanged={r.unchanged} updated={r.updated} total={r.total}"
        )

    print("=" * 60)
    print("Generate feed XML artifacts (gzip)")
    stats = _generate_feed_xml_artifacts(dest)
    for name, s in stats.items():
        print(
            f"  {name}: jobs={s['job_count']} gzip={s['bytes_gzip']} at={s['generated_at']}"
        )
    print("DONE")


if __name__ == "__main__":
    main()
