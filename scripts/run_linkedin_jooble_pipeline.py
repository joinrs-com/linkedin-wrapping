#!/usr/bin/env python3
"""
Esegue il refresh di job_posting_pre (DELETE + INSERT da job_postings_1 / employers)
e poi improve_job_descriptions (OpenAI + sync verso job_postings).

Uso: dalla root del repo, con DATABASE_URL e OPENAI_API_KEY in ambiente o in .env:
    python scripts/run_linkedin_jooble_pipeline.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "scripts"))

load_dotenv(project_root / ".env" if (project_root / ".env").exists() else None)

import improve_job_descriptions as ijd  # noqa: E402

def _mysql_identifier(name: str) -> str:
    """Allow only safe MySQL database/schema identifiers (letters, digits, _)."""
    if not name or not name.replace("_", "").isalnum():
        raise ValueError(f"Identificatore MySQL non valido: {name!r}")
    return name


def _apply_job_feed_db_qualifiers(sql: str) -> str:
    """
    In MySQL `db.table`: il primo segmento è il NOME DEL DATABASE.
    La query versionata usa job_postings.job_postings_1 e employers.employers;
    se sul tuo server i cataloghi hanno altri nomi, imposta le env sotto.
    """
    jp = _mysql_identifier(os.getenv("JOB_FEED_DB_JOB_POSTINGS", "job_postings"))
    em = _mysql_identifier(os.getenv("JOB_FEED_DB_EMPLOYERS", "employers"))
    sql = sql.replace("job_postings.job_postings_1", f"{jp}.job_postings_1")
    sql = sql.replace("employers.employers", f"{em}.employers")
    return sql



def main() -> None:
    if not os.getenv("DATABASE_URL"):
        raise SystemExit("DATABASE_URL non impostata")
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY non impostata")

    sql_path = project_root / "scripts" / "sql" / "refresh_job_posting_pre_insert.sql"
    if not sql_path.is_file():
        raise SystemExit(f"File SQL mancante: {sql_path}")

    insert_sql = sql_path.read_text(encoding="utf-8")
    insert_sql = _apply_job_feed_db_qualifiers(insert_sql)

    engine = ijd.create_database_engine()
    if engine.dialect.name != "mysql":
        raise SystemExit("Questa pipeline supporta solo MySQL (INSERT cross-schema).")

    print("=" * 60)
    print("Pipeline LinkedIn/Jooble: refresh job_posting_pre")
    print("=" * 60)

    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("DELETE FROM job_posting_pre"))
            conn.execute(text(insert_sql))

    print("Refresh job_posting_pre completato.\n")

    ijd.main()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(f"Errore pipeline: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
