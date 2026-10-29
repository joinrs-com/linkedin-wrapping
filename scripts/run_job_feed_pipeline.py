#!/usr/bin/env python3
"""
Pipeline incrementale feed job: sync export senza TRUNCATE (OpenAI enrichment skipped).

Uso:
    DATABASE_URL                    → joinrs-intelligence/lw (destinazione)
    JOB_FEED_SOURCE_DATABASE_URL    → mysql-production01 (sorgente)

    python scripts/run_job_feed_pipeline.py
    python scripts/run_job_feed_pipeline.py --feeds jooble,adzuna
    python scripts/run_job_feed_pipeline.py --refresh-descriptions
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
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
    backfill_jooble_description_talent,
    create_mysql_engine,
    load_sql,
    sync_feed_table,
    upsert_feed_xml_artifact,
)
from api.platforms.talent import normalize_description_for_talent  # noqa: E402
from api.wrapping.models import (  # noqa: E402
    AdzunaJobFeed,
    JobFeedPipelineRun,
    JoobleJobFeed,
)
from api.wrapping.wrapping import (  # noqa: E402
    generate_adzuna_xml,
    generate_wrapping_xml,
)
from feed_buckets import BUCKETS, artifact_name, legacy_root_artifact_name  # noqa: E402
from sqlmodel import select  # noqa: E402


@dataclass
class FeedConfig:
    name: str
    table: str
    sql_file: str
    columns: list[str]
    id_column: str
    description_column: str | None = None
    string_id: bool = False
    # Talent-style HTML normalize + refresh description on existing rows
    normalize_html: bool = False
    # Opt-in via --refresh-descriptions (cold populate should skip).
    refresh_descriptions: bool = False
    # Slim catalog SELECT + fetch description only for new job_posting_id.
    two_phase_descriptions: bool = False


FEED_CONFIGS: list[FeedConfig] = [
    FeedConfig(
        name="jooble",
        table="jooble_job_feed",
        sql_file="jooble_job_feed_select.sql",
        columns=[
            "id",
            "job_posting_id",
            "position",
            "employers_name",
            "employers_id",
            "priority",
            "description",
            "description_talent",
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
            "salary",
            "country_code",
            "bucket",
        ],
        id_column="id",
        description_column="description",
        string_id=True,
        normalize_html=True,
        refresh_descriptions=False,
        two_phase_descriptions=True,
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
            "salary",
        ],
        id_column="id",
        description_column="description",
    ),
    FeedConfig(
        name="adzuna",
        table="adzuna_job_feed",
        sql_file="adzuna_job_feed_select.sql",
        columns=[
            "id",
            "job_posting_id",
            "title",
            "description",
            "url",
            "location",
            "country",
            "remote",
            "salary",
            "company",
            "category",
            "date",
            "cpc",
            "priority",
            "country_code",
            "bucket",
        ],
        id_column="id",
        description_column="description",
        string_id=True,
        normalize_html=True,
        refresh_descriptions=False,
        two_phase_descriptions=True,
    ),
    FeedConfig(
        name="jobrapido",
        table="jobrapido_job_feed",
        sql_file="jobrapido_job_feed_select.sql",
        columns=[
            "reference_id",
            "job_posting_id",
            "title",
            "description",
            "url",
            "location",
            "state",
            "country",
            "postalcode",
            "company",
            "website",
            "publishdate",
            "expirydate",
            "salary",
            "education",
            "jobtype",
            "category",
            "experience",
            "cpc",
            "priority",
        ],
        id_column="reference_id",
        description_column="description",
        string_id=True,
    ),
    # jooble_abroad_job_feed sync removed: content lives in jooble_job_feed buckets usa|eu3|row
]


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _generate_feed_xml_artifacts(dest_engine) -> dict[str, dict]:
    """Build gzip XML per platform × campaign bucket (+ legacy root aliases)."""
    stats: dict[str, dict] = {}
    with Session(dest_engine) as session:
        jooble_by_bucket: dict[str, list] = {b: [] for b in BUCKETS}
        for row in session.exec(select(JoobleJobFeed)).all():
            b = getattr(row, "bucket", None) or "row"
            jooble_by_bucket.setdefault(b, []).append(row)

        adzuna_by_bucket: dict[str, list] = {b: [] for b in BUCKETS}
        for row in session.exec(select(AdzunaJobFeed)).all():
            b = getattr(row, "bucket", None) or "row"
            adzuna_by_bucket.setdefault(b, []).append(row)

    builds: list[tuple[str, str, int]] = []
    for bucket in BUCKETS:
        j_rows = jooble_by_bucket.get(bucket, [])
        a_rows = adzuna_by_bucket.get(bucket, [])
        builds.append(
            (
                artifact_name("jooble", bucket),
                generate_wrapping_xml(
                    j_rows,
                    apply_url_mode="jooble",
                    prefer_employers_name_as_company=True,
                    include_priority=True,
                    include_employers_id=True,
                    include_country_code=True,
                ),
                len(j_rows),
            )
        )
        builds.append(
            (
                artifact_name("talent", bucket),
                generate_wrapping_xml(
                    j_rows,
                    apply_url_mode="jooble",
                    prefer_employers_name_as_company=True,
                    include_priority=True,
                    include_employers_id=True,
                    include_country_code=True,
                    description_sanitizer=normalize_description_for_talent,
                ),
                len(j_rows),
            )
        )
        builds.append(
            (
                artifact_name("adzuna", bucket),
                generate_adzuna_xml(a_rows),
                len(a_rows),
            )
        )

    # Compat: /wrapping/jooble|talent|adzuna still resolve artifact keys without suffix
    for platform in ("jooble", "talent", "adzuna"):
        src_key = artifact_name(platform, "ita_esp")
        for feed_name, xml_text, job_count in list(builds):
            if feed_name == src_key:
                builds.append((legacy_root_artifact_name(platform), xml_text, job_count))
                break

    # Compat: /wrapping/jooble/abroad → usa∪eu3∪row (deprecated; prefer /us /eu3 /row)
    abroad_rows: list = []
    for b in ("usa", "eu3", "row"):
        abroad_rows.extend(jooble_by_bucket.get(b, []))
    builds.append(
        (
            "jooble_abroad",
            generate_wrapping_xml(
                abroad_rows,
                apply_url_mode="jooble",
                prefer_employers_name_as_company=True,
                include_priority=True,
                include_employers_id=True,
                include_countries=True,
                include_country_code=True,
            ),
            len(abroad_rows),
        )
    )

    with dest_engine.connect() as dest_conn:
        for feed_name, xml_text, job_count in builds:
            stats[feed_name] = upsert_feed_xml_artifact(
                dest_conn,
                feed_name=feed_name,
                xml_text=xml_text,
                job_count=job_count,
            )
    return stats


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
                "updated": r.updated,
                "total": r.total,
            }
            for name, r in feed_results.items()
        },
    }
    if error_message:
        report["error_message"] = error_message
    return report


def _feed_or_zero(feeds: dict[str, SyncResult], name: str) -> SyncResult:
    return feeds.get(name) or SyncResult(0, 0, 0, 0, 0)


def _save_run_report(dest_engine, report: dict, enrichment: ijd.EnrichmentResult, feed_results: dict[str, SyncResult]) -> None:
    feeds = feed_results
    jooble = _feed_or_zero(feeds, "jooble")
    whatjobs = _feed_or_zero(feeds, "whatjobs")
    hirematic = _feed_or_zero(feeds, "hirematic")
    adzuna = _feed_or_zero(feeds, "adzuna")
    jobrapido = _feed_or_zero(feeds, "jobrapido")
    jooble_abroad = _feed_or_zero(feeds, "jooble_abroad")
    with Session(dest_engine) as session:
        row = JobFeedPipelineRun(
            started_at=datetime.fromisoformat(report["started_at"]),
            finished_at=datetime.fromisoformat(report["finished_at"]),
            duration_sec=report["duration_sec"],
            status=report["status"],
            openai_processed=enrichment.processed,
            enriched_deleted=enrichment.deleted,
            enriched_total=enrichment.total,
            linkedin_active=0,
            linkedin_inserted=0,
            linkedin_deleted=0,
            linkedin_total=0,
            jooble_inserted=jooble.inserted,
            jooble_deleted=jooble.deleted,
            jooble_total=jooble.total,
            whatjobs_inserted=whatjobs.inserted,
            whatjobs_deleted=whatjobs.deleted,
            whatjobs_total=whatjobs.total,
            hirematic_inserted=hirematic.inserted,
            hirematic_deleted=hirematic.deleted,
            hirematic_total=hirematic.total,
            adzuna_inserted=adzuna.inserted,
            adzuna_deleted=adzuna.deleted,
            adzuna_total=adzuna.total,
            jobrapido_inserted=jobrapido.inserted,
            jobrapido_deleted=jobrapido.deleted,
            jobrapido_total=jobrapido.total,
            jooble_abroad_inserted=jooble_abroad.inserted,
            jooble_abroad_deleted=jooble_abroad.deleted,
            jooble_abroad_total=jooble_abroad.total,
            error_message=report.get("error_message"),
        )
        session.add(row)
        session.commit()


def run_pipeline(
    *,
    feed_names: list[str] | None = None,
    refresh_descriptions: bool | None = None,
) -> dict:
    if not os.getenv("DATABASE_URL"):
        raise SystemExit("DATABASE_URL non impostata")
    if not os.getenv("JOB_FEED_SOURCE_DATABASE_URL"):
        raise SystemExit("JOB_FEED_SOURCE_DATABASE_URL non impostata")

    started_at = _utc_now_naive()
    dest_engine = ijd.create_database_engine()
    src_engine = create_mysql_engine(os.environ["JOB_FEED_SOURCE_DATABASE_URL"])

    enrichment = ijd.EnrichmentResult(processed=0, deleted=0, total=0, eligible_active=0)
    feed_results: dict[str, SyncResult] = {}

    configs = FEED_CONFIGS
    if feed_names:
        wanted = {n.strip().lower() for n in feed_names if n.strip()}
        known = {c.name for c in FEED_CONFIGS}
        unknown = wanted - known
        if unknown:
            raise SystemExit(
                f"Feed sconosciuti: {sorted(unknown)}. Validi: {sorted(known)}"
            )
        configs = [c for c in FEED_CONFIGS if c.name in wanted]

    try:
        # Fresh connections per phase: long-lived sockets die on MySQL wait_timeout
        # (seen as OperationalError 2013 during Sync adzuna after multi-hour runs).
        print("=" * 60)
        print("Job feed pipeline — OpenAI enrichment skipped")
        print("=" * 60)
        print(f"Feeds: {', '.join(c.name for c in configs)}")
        if refresh_descriptions is True:
            print("Description refresh: ON (--refresh-descriptions)")
        else:
            print("Description refresh: OFF (default; pass --refresh-descriptions)")
        enriched: dict[int, str] = {}

        for cfg in configs:
            do_refresh = (
                refresh_descriptions
                if refresh_descriptions is not None
                else cfg.refresh_descriptions
            )
            print("=" * 60)
            print(f"Sync {cfg.name} ({cfg.table})")
            print("=" * 60)
            select_sql = load_sql(project_root, cfg.sql_file)
            with src_engine.connect() as src_conn, dest_engine.connect() as dest_conn:
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
                    normalize_html=cfg.normalize_html,
                    refresh_descriptions=do_refresh,
                    two_phase_descriptions=cfg.two_phase_descriptions,
                )
            feed_results[cfg.name] = result
            print(
                f"  active={result.active} inserted={result.inserted} "
                f"deleted={result.deleted} unchanged={result.unchanged} "
                f"updated={result.updated} total={result.total}"
            )
            if cfg.name == "jooble":
                print("=" * 60)
                print("Backfill jooble description_talent (NULL only)")
                print("=" * 60)
                with dest_engine.connect() as dest_conn:
                    n = backfill_jooble_description_talent(dest_conn)
                print(f"  description_talent backfilled={n}")

        print("=" * 60)
        print("Generate feed XML artifacts (gzip)")
        print("=" * 60)
        artifact_stats = _generate_feed_xml_artifacts(dest_engine)
        for name, stats in artifact_stats.items():
            print(
                f"  {name}: jobs={stats['job_count']} "
                f"raw={stats['bytes_uncompressed']} gzip={stats['bytes_gzip']}"
            )

        finished_at = _utc_now_naive()
        report = _build_report(
            started_at=started_at,
            finished_at=finished_at,
            status="success",
            enrichment=enrichment,
            feed_results=feed_results,
        )
        report["artifacts"] = artifact_stats
        _save_run_report(dest_engine, report, enrichment, feed_results)
        print("\n" + json.dumps(report, indent=2, ensure_ascii=False))
        return report

    except Exception as e:
        finished_at = _utc_now_naive()
        partial = feed_results or {c.name: SyncResult(0, 0, 0, 0, 0) for c in configs}
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Incremental job feed sync pipeline")
    parser.add_argument(
        "--feeds",
        default="",
        help="Comma-separated feed names (default: all). Example: jooble,adzuna",
    )
    parser.add_argument(
        "--refresh-descriptions",
        action="store_true",
        help="Also UPDATE descriptions on existing rows (slow; off by default)",
    )
    args = parser.parse_args(argv)
    feed_names = [p for p in args.feeds.split(",") if p.strip()] or None
    run_pipeline(
        feed_names=feed_names,
        refresh_descriptions=True if args.refresh_descriptions else None,
    )


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(1)
