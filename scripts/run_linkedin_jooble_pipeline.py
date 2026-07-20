#!/usr/bin/env python3
"""
Esegue il refresh di job_posting_pre (DELETE + dati da job_postings_1 / employers)
e poi improve_job_descriptions (OpenAI + sync verso job_postings).

Uso (una connessione, stesso server MySQL):
    DATABASE_URL, OPENAI_API_KEY, opzionalmente JOB_FEED_DB_*

Due server MySQL diversi (es. production lettura + joinrs-intelligence scrittura):
    DATABASE_URL          → host destinazione (lw: job_posting_pre, job_postings)
    JOB_FEED_SOURCE_DATABASE_URL → host sorgente (job_postings DB + employers DB)
    JOB_FEED_DB_JOB_POSTINGS / JOB_FEED_DB_EMPLOYERS → nomi catalog MySQL sulla sorgente
    OPENAI_API_KEY (solo se, dopo il refresh, esistono nuovi annunci che richiedono il miglioramento OpenAI)

Il file `.env` nella root del repo viene caricato con priorità sulle variabili già esportate nel terminale,
così URL DB sbagliati nella shell non oscurano il `.env` corretto.

Comando: python scripts/run_linkedin_jooble_pipeline.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "scripts"))

# override=True: il .env del repo deve vincere su variabili già esportate nel terminale (evita URL tronchi).
_env_file = project_root / ".env"
if _env_file.is_file():
    load_dotenv(_env_file, override=True)

import improve_job_descriptions as ijd  # noqa: E402

JOB_POSTING_PRE_COLUMNS = [
    "position",
    "job_description",
    "company",
    "employers_name",
    "employers_id",
    "priority",
    "apply_url",
    "company_id",
    "location",
    "workplace_types",
    "experience_level",
    "jobtype",
    "partner_job_id",
    "last_build_date",
]


def _mysql_identifier(name: str) -> str:
    if not name or not name.replace("_", "").isalnum():
        raise ValueError(f"Identificatore MySQL non valido: {name!r}")
    return name


def _apply_job_feed_db_qualifiers(sql: str) -> str:
    jp = _mysql_identifier(os.getenv("JOB_FEED_DB_JOB_POSTINGS", "job_postings"))
    em = _mysql_identifier(os.getenv("JOB_FEED_DB_EMPLOYERS", "employers"))
    sql = sql.replace("job_postings.job_postings_1", f"{jp}.job_postings_1")
    sql = sql.replace("employers.employers", f"{em}.employers")
    return sql


def _extract_select_sql(full_sql: str) -> str:
    key = "WITH employer_counts AS"
    idx = full_sql.find(key)
    if idx == -1:
        raise ValueError(
            "Impossibile estrarre la SELECT dal file SQL (manca 'WITH employer_counts AS')."
        )
    return full_sql[idx:].strip()


def _create_plain_mysql_engine(url: str):
    eng = create_engine(
        url,
        pool_recycle=3600,
        pool_pre_ping=True,
        echo=False,
        connect_args={"check_same_thread": False} if "sqlite" in url else {},
    )
    if eng.dialect.name != "mysql":
        raise ValueError("Atteso MySQL in JOB_FEED_SOURCE_DATABASE_URL")
    return eng


def _bulk_insert_job_posting_pre(conn, rows: list) -> None:
    if not rows:
        print("Nessuna riga dalla sorgente dopo i filtri WHERE.")
        return
    col_sql = ", ".join(JOB_POSTING_PRE_COLUMNS)
    ph = ", ".join(f":{c}" for c in JOB_POSTING_PRE_COLUMNS)
    stmt = text(f"INSERT INTO job_posting_pre ({col_sql}) VALUES ({ph})")
    n = 0
    for row in rows:
        m = row._mapping
        payload = {c: m[c] for c in JOB_POSTING_PRE_COLUMNS}
        conn.execute(stmt, payload)
        n += 1
    print(f"Inserite {n} righe in job_posting_pre.")


def _refresh_pre_two_servers(insert_sql_full: str) -> None:
    src_url = os.environ["JOB_FEED_SOURCE_DATABASE_URL"]
    select_sql = _extract_select_sql(insert_sql_full)

    print("Modalità due server: SELECT sulla sorgente, INSERT sulla destinazione.")

    src_eng = _create_plain_mysql_engine(src_url)
    dest_eng = ijd.create_database_engine()

    with src_eng.connect() as src_conn:
        result = src_conn.execute(text(select_sql))
        rows = result.fetchall()

    with dest_eng.connect() as dest_conn:
        with dest_conn.begin():
            dest_conn.execute(text("DELETE FROM job_posting_pre"))
            _bulk_insert_job_posting_pre(dest_conn, rows)


def _refresh_pre_one_server(insert_sql: str) -> None:
    engine = ijd.create_database_engine()
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("DELETE FROM job_posting_pre"))
            conn.execute(text(insert_sql))


def main() -> None:
    print(
        "DEPRECATO: usa scripts/run_job_feed_pipeline.py (sync incrementale, senza job_posting_pre).",
        file=sys.stderr,
    )
    if not os.getenv("DATABASE_URL"):
        raise SystemExit("DATABASE_URL non impostata")

    sql_path = project_root / "scripts" / "sql" / "refresh_job_posting_pre_insert.sql"
    if not sql_path.is_file():
        raise SystemExit(f"File SQL mancante: {sql_path}")

    insert_sql = sql_path.read_text(encoding="utf-8")
    insert_sql = _apply_job_feed_db_qualifiers(insert_sql)

    dest_engine = ijd.create_database_engine()
    if dest_engine.dialect.name != "mysql":
        raise SystemExit("La destinazione DATABASE_URL deve essere MySQL.")

    print("=" * 60)
    print("Pipeline LinkedIn/Jooble: refresh job_posting_pre")
    print("=" * 60)

    if os.getenv("JOB_FEED_SOURCE_DATABASE_URL"):
        _refresh_pre_two_servers(insert_sql)
    else:
        _refresh_pre_one_server(insert_sql)

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
