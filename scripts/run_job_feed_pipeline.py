#!/usr/bin/env python3
"""
Pipeline incrementale feed job: OpenAI su job nuovi P1-3 Italia, sync export senza TRUNCATE.

Uso:
    DATABASE_URL                    → joinrs-intelligence/lw (destinazione)
    JOB_FEED_SOURCE_DATABASE_URL    → mysql-production01 (sorgente)
    OPENAI_API_KEY

    python scripts/run_job_feed_pipeline.py
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text
from sqlmodel import Session

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "scripts"))

_env_file = project_root / ".env"
if _env_file.is_file():
    load_dotenv(_env_file, override=True)

import improve_job_descriptions as ijd  # noqa: E402
from job_feed_common import (  # noqa: E402
    SyncResult,
    create_mysql_engine,
    load_enriched_descriptions,
    load_sql,
    sync_feed_table,
)
from api.wrapping.models import JobFeedPipelineRun  # noqa: E402


@dataclass
class FeedConfig:
    name: str
    table: str
    sql_file: str
    columns: list[str]
    id_column: str
    description_column: str | None = None
    string_id: bool = False


FEED_CONFIGS: list[FeedConfig] = [
    FeedConfig(
        name="linkedin",
        table="job_postings",
        sql_file="job_postings_select.sql",
        columns=[
            "position",
            "description",
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
        ],
        id_column="partner_job_id",
        description_column="description",
        string_id=True,
    ),
    FeedConfig(
        name="jooble",
        table="jooble_job_feed",
        sql_file="jooble_job_feed_select.sql",
        columns=[
            "id",
            "position",
            "employers_name",
            "employers_id",
            "priority",
            "description",
            "company",
            "apply_url",
            "company_id",
            "location",
            "countries",
            "workplace_types",
            "experience_level",
            "jobtype",
            "partner_job_id",
            "last_build_date",
        ],
        id_column="id",
        description_column="description",
    ),
    FeedConfig(
        name="whatjobs",
        table="whatjobs_job_feed",
        sql_file="whatjobs_job_feed_select.sql",
        columns=[
            "id",
            "link",
            "name",
            "region",
            "remote",
            "salary",
            "description",
            "company",
            "company_logo",
            "pubdate",
            "updated",
            "expire",
            "jobtype",
            "employers_id",
            "priority",
            "experience_level",
        ],
        id_column="id",
        description_column="description",
    ),
    FeedConfig(
        name="hirematic",
        table="hirematic_job_feed",
        sql_file="hirematic_job_feed_select.sql",
        columns=[
            "id",
            "title",
            "city",
            "state",
            "zip",
            "country",
            "post_date",
            "company",
            "priority",
            "category",
            "url",
            "description",
            "cpc",
        ],
        id_column="id",
        description_column="description",
    ),
]


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fetch_enrichment_inputs(source_conn) -> list[dict]:
    sql = load_sql(project_root, "job_enrichment_input_select.sql")
    rows = source_conn.execute(text(sql)).fetchall()
    return [dict(r._mapping) for r in rows]


def _build_report(
    *,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    enrichment: ijd.EnrichmentResult,
    feed_results: dict[str, SyncResult],
    error_message: str | None = None,
) -> dict:
    duration = int((finished_at - started_at).total_seconds())
    report = {
        "status": status,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_sec": duration,
        "openai": {
            "processed": enrichment.processed,
            "deleted": enrichment.deleted,
            "total": enrichment.total,
            "eligible_active": enrichment.eligible_active,
        },
        "feeds": {
            name: {
                "active": r.active,
                "inserted": r.inserted,
                "deleted": r.deleted,
                "unchanged": r.unchanged,
                "total": r.total,
            }
            for name, r in feed_results.items()
        },
    }
    if error_message:
        report["error_message"] = error_message
    return report


def _save_run_report(dest_engine, report: dict, enrichment: ijd.EnrichmentResult, feed_results: dict[str, SyncResult]) -> None:
    feeds = feed_results
    with Session(dest_engine) as session:
        row = JobFeedPipelineRun(
            started_at=datetime.fromisoformat(report["started_at"]),
            finished_at=datetime.fromisoformat(report["finished_at"]),
            duration_sec=report["duration_sec"],
            status=report["status"],
            openai_processed=enrichment.processed,
            enriched_deleted=enrichment.deleted,
            enriched_total=enrichment.total,
            linkedin_active=feeds["linkedin"].active,
            linkedin_inserted=feeds["linkedin"].inserted,
            linkedin_deleted=feeds["linkedin"].deleted,
            linkedin_total=feeds["linkedin"].total,
            jooble_inserted=feeds["jooble"].inserted,
            jooble_deleted=feeds["jooble"].deleted,
            jooble_total=feeds["jooble"].total,
            whatjobs_inserted=feeds["whatjobs"].inserted,
            whatjobs_deleted=feeds["whatjobs"].deleted,
            whatjobs_total=feeds["whatjobs"].total,
            hirematic_inserted=feeds["hirematic"].inserted,
            hirematic_deleted=feeds["hirematic"].deleted,
            hirematic_total=feeds["hirematic"].total,
            error_message=report.get("error_message"),
        )
        session.add(row)
        session.commit()


def run_pipeline() -> dict:
    if not os.getenv("DATABASE_URL"):
        raise SystemExit("DATABASE_URL non impostata")
    if not os.getenv("JOB_FEED_SOURCE_DATABASE_URL"):
        raise SystemExit("JOB_FEED_SOURCE_DATABASE_URL non impostata")

    started_at = _utc_now_naive()
    dest_engine = ijd.create_database_engine()
    src_engine = create_mysql_engine(os.environ["JOB_FEED_SOURCE_DATABASE_URL"])

    enrichment = ijd.EnrichmentResult(processed=0, deleted=0, total=0, eligible_active=0)
    feed_results: dict[str, SyncResult] = {}

    try:
        with src_engine.connect() as src_conn, dest_engine.connect() as dest_conn:
            print("=" * 60)
            print("Job feed pipeline — enrichment")
            print("=" * 60)
            enrichment_inputs = _fetch_enrichment_inputs(src_conn)
            print(f"Job eleggibili attivi in produzione: {len(enrichment_inputs)}")
            enrichment = ijd.run_enrichment_pipeline(enrichment_inputs, engine=dest_engine)

            enriched = load_enriched_descriptions(dest_conn)
            print(f"job_description_enriched: {len(enriched)} righe\n")

            for cfg in FEED_CONFIGS:
                print("=" * 60)
                print(f"Sync {cfg.name} ({cfg.table})")
                print("=" * 60)
                select_sql = load_sql(project_root, cfg.sql_file)
                result = sync_feed_table(
                    dest_conn,
                    src_conn,
                    table=cfg.table,
                    select_sql=select_sql,
                    columns=cfg.columns,
                    id_column=cfg.id_column,
                    description_column=cfg.description_column,
                    enriched=enriched,
                    string_id=cfg.string_id,
                )
                feed_results[cfg.name] = result
                print(
                    f"  active={result.active} inserted={result.inserted} "
                    f"deleted={result.deleted} unchanged={result.unchanged} total={result.total}"
                )

        finished_at = _utc_now_naive()
        report = _build_report(
            started_at=started_at,
            finished_at=finished_at,
            status="success",
            enrichment=enrichment,
            feed_results=feed_results,
        )
        _save_run_report(dest_engine, report, enrichment, feed_results)
        print("\n" + json.dumps(report, indent=2, ensure_ascii=False))
        return report

    except Exception as e:
        finished_at = _utc_now_naive()
        partial = feed_results or {c.name: SyncResult(0, 0, 0, 0, 0) for c in FEED_CONFIGS}
        error_message = str(e)
        if isinstance(e, ijd.OpenAIEnrichmentError):
            error_message = (
                f"OpenAI enrichment aborted: {e}. "
                "Fix OPENAI_API_KEY and TRUNCATE job_description_enriched if needed before retry."
            )
        report = _build_report(
            started_at=started_at,
            finished_at=finished_at,
            status="failed",
            enrichment=enrichment,
            feed_results=partial,
            error_message=error_message,
        )
        try:
            _save_run_report(dest_engine, report, enrichment, partial)
        except Exception:
            pass
        print(json.dumps(report, indent=2, ensure_ascii=False), file=sys.stderr)
        traceback.print_exc()
        raise


def main() -> None:
    run_pipeline()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(1)
