#!/usr/bin/env python3
"""
Pipeline incrementale feed job: sync export senza TRUNCATE.

Uso:
    DATABASE_URL                    → joinrs-intelligence/lw (destinazione)
    JOB_FEED_SOURCE_DATABASE_URL    → mysql-production01 (sorgente)

    python scripts/run_job_feed_pipeline.py
    python scripts/run_job_feed_pipeline.py --feeds jooble,adzuna
    python scripts/run_job_feed_pipeline.py --refresh-descriptions
    python scripts/run_job_feed_pipeline.py --artifacts-only
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from dotenv import load_dotenv
from sqlalchemy import or_, text
from sqlmodel import Session, SQLModel, select

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "scripts"))

_env_file = project_root / ".env"
if _env_file.is_file():
    load_dotenv(_env_file, override=True)

from feed_database import create_database_engine  # noqa: E402
from feed_alerts import notify_pipeline_result  # noqa: E402
from job_feed_common import (  # noqa: E402
    SyncResult,
    backfill_jooble_description_talent,
    campaign_artifact_feed_names,
    check_feed_xml_artifact_integrity,
    create_mysql_engine,
    load_sql,
    purge_archived_job_postings_from_feeds,
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
from feed_buckets import FEEDS, artifact_name  # noqa: E402


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


_FeedRowT = TypeVar("_FeedRowT", bound=SQLModel)
_ARTIFACT_LOAD_CHUNK = 2_000


def _bucket_where(model: type[SQLModel], bucket: str):
    """Match campaign feed key; NULL/empty fold into Italy P1–4 (``it``)."""
    if bucket == "it":
        return or_(model.bucket == "it", model.bucket.is_(None), model.bucket == "")  # type: ignore[attr-defined]
    return model.bucket == bucket  # type: ignore[attr-defined]


def _load_feed_bucket(
    engine,
    model: type[_FeedRowT],
    bucket: str,
    *,
    chunk_size: int = _ARTIFACT_LOAD_CHUNK,
) -> list[_FeedRowT]:
    """Keyset-paginate a single bucket so huge catalogs don't kill one SELECT.

    Feed PKs are strings; paginate lexicographically on id.
    """
    table = getattr(model, "__tablename__", model.__name__)
    print(f"  loading {table}/{bucket}…", flush=True)
    rows: list[_FeedRowT] = []
    last_id = ""
    while True:
        batch: list[_FeedRowT] = []
        for attempt in range(1, 4):
            try:
                with Session(engine) as session:
                    stmt = (
                        select(model)
                        .where(_bucket_where(model, bucket), model.id > last_id)  # type: ignore[attr-defined]
                        .order_by(model.id)  # type: ignore[attr-defined]
                        .limit(chunk_size)
                    )
                    batch = list(session.exec(stmt).all())
                    session.expunge_all()
                break
            except Exception as exc:  # noqa: BLE001 — retry transient MySQL drops
                if attempt >= 3 or "Lost connection" not in str(exc):
                    raise
                wait = 5 * attempt
                print(
                    f"    … {table}/{bucket} chunk retry {attempt}/3 after {exc.__class__.__name__}; "
                    f"sleep {wait}s",
                    flush=True,
                )
                time.sleep(wait)
        if not batch:
            break
        last_id = str(batch[-1].id)  # type: ignore[attr-defined]
        rows.extend(batch)
        if len(rows) % 10_000 < chunk_size:
            print(f"    … {table}/{bucket}: {len(rows)} rows", flush=True)
    print(f"  loaded {table}/{bucket}: {len(rows)} rows", flush=True)
    return rows


def _upsert_xml_artifact(
    dest_conn,
    *,
    feed_name: str,
    rows: list,
    job_count: int,
    builder,
) -> dict:
    """Generate full XML (no description trim) and UPSERT gzip into MySQL."""
    xml_text = builder(rows)
    try:
        return upsert_feed_xml_artifact(
            dest_conn,
            feed_name=feed_name,
            xml_text=xml_text,
            job_count=job_count,
        )
    finally:
        del xml_text


def _artifact_platforms_for_feeds(feed_names: list[str] | None) -> set[str] | None:
    """Map pipeline feed names → XML platforms. None = all platforms."""
    if not feed_names:
        return None
    out: set[str] = set()
    for name in feed_names:
        n = name.strip().lower()
        if n == "jooble":
            out.update(("jooble", "talent"))
        elif n == "adzuna":
            out.add("adzuna")
        else:
            out.add(n)
    return out or None


def _generate_feed_xml_artifacts(
    dest_engine,
    *,
    platforms: set[str] | None = None,
) -> dict[str, dict]:
    """Build gzip XML per platform × feed key.

    Loads one feed at a time (chunked). Full descriptions; MySQL LONGBLOB payload.
    platforms: optional subset of {"jooble","talent","adzuna"}; None = all.
    """
    want = platforms or {"jooble", "talent", "adzuna"}
    stats: dict[str, dict] = {}

    def _jooble_xml(rows: list) -> str:
        return generate_wrapping_xml(
            rows,
            apply_url_mode="jooble",
            prefer_employers_name_as_company=True,
            include_priority=True,
            include_employers_id=True,
            include_country_code=True,
        )

    def _talent_xml(rows: list) -> str:
        return generate_wrapping_xml(
            rows,
            apply_url_mode="jooble",
            prefer_employers_name_as_company=True,
            include_priority=True,
            include_employers_id=True,
            include_country_code=True,
            description_sanitizer=normalize_description_for_talent,
        )

    def _adzuna_xml(rows: list) -> str:
        return generate_adzuna_xml(rows)

    with dest_engine.connect() as dest_conn:
        for feed in FEEDS:
            print(f"\n-- artifacts for feed={feed} --", flush=True)
            if "jooble" in want or "talent" in want:
                j_rows = _load_feed_bucket(dest_engine, JoobleJobFeed, feed)
                if "jooble" in want:
                    stats[artifact_name("jooble", feed)] = _upsert_xml_artifact(
                        dest_conn,
                        feed_name=artifact_name("jooble", feed),
                        rows=j_rows,
                        job_count=len(j_rows),
                        builder=_jooble_xml,
                    )
                if "talent" in want:
                    stats[artifact_name("talent", feed)] = _upsert_xml_artifact(
                        dest_conn,
                        feed_name=artifact_name("talent", feed),
                        rows=j_rows,
                        job_count=len(j_rows),
                        builder=_talent_xml,
                    )
                del j_rows
                gc.collect()

            if "adzuna" in want:
                a_rows = _load_feed_bucket(dest_engine, AdzunaJobFeed, feed)
                stats[artifact_name("adzuna", feed)] = _upsert_xml_artifact(
                    dest_conn,
                    feed_name=artifact_name("adzuna", feed),
                    rows=a_rows,
                    job_count=len(a_rows),
                    builder=_adzuna_xml,
                )
                del a_rows
                gc.collect()
    return stats


def _assert_artifact_integrity(dest_engine, *, platforms: set[str] | None) -> None:
    want = tuple(sorted(platforms)) if platforms else ("adzuna", "jooble", "talent")
    names = campaign_artifact_feed_names(want)  # type: ignore[arg-type]
    with dest_engine.connect() as conn:
        failures = check_feed_xml_artifact_integrity(
            conn, feed_names=names, gunzip=True
        )
    if failures:
        preview = ", ".join(
            f"{f.get('feed_name')}:{f.get('error')}" for f in failures[:12]
        )
        more = f" (+{len(failures) - 12} more)" if len(failures) > 12 else ""
        raise RuntimeError(
            f"feed_xml_artifact integrity failed for {len(failures)} feeds: "
            f"{preview}{more}"
        )
    print(
        f"  artifact integrity OK ({len(names)} feeds checked)",
        flush=True,
    )


def _build_report(
    *,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    feed_results: dict[str, SyncResult],
    error_message: str | None = None,
) -> dict:
    duration = int((finished_at - started_at).total_seconds())
    report = {
        "status": status,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_sec": duration,
        # Keep legacy report fields compatible with historical pipeline runs.
        "openai": {
            "processed": 0,
            "deleted": 0,
            "total": 0,
            "eligible_active": 0,
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


def _save_run_report(dest_engine, report: dict, feed_results: dict[str, SyncResult]) -> None:
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
            openai_processed=0,
            enriched_deleted=0,
            enriched_total=0,
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
    artifacts_only: bool = False,
    skip_artifacts: bool = False,
) -> dict:
    if not os.getenv("DATABASE_URL"):
        raise SystemExit("DATABASE_URL non impostata")
    if not artifacts_only and not os.getenv("JOB_FEED_SOURCE_DATABASE_URL"):
        raise SystemExit("JOB_FEED_SOURCE_DATABASE_URL non impostata")
    if artifacts_only and skip_artifacts:
        raise SystemExit("Non usare insieme --artifacts-only e --skip-artifacts")
    artifact_platforms = _artifact_platforms_for_feeds(feed_names)

    started_at = _utc_now_naive()
    dest_engine = create_database_engine()
    feed_results: dict[str, SyncResult] = {}

    if artifacts_only:
        print("=" * 60)
        print("Generate feed XML artifacts only (gzip)")
        if artifact_platforms:
            print(f"Platforms: {', '.join(sorted(artifact_platforms))}")
        print("=" * 60)
        try:
            artifact_stats = _generate_feed_xml_artifacts(
                dest_engine, platforms=artifact_platforms
            )
            for name, stats in artifact_stats.items():
                print(
                    f"  {name}: jobs={stats['job_count']} "
                    f"raw={stats['bytes_uncompressed']} gzip={stats['bytes_gzip']}"
                )
            print("=" * 60)
            print("Verify feed XML artifact integrity")
            print("=" * 60)
            _assert_artifact_integrity(dest_engine, platforms=artifact_platforms)
            finished_at = _utc_now_naive()
            report = _build_report(
                started_at=started_at,
                finished_at=finished_at,
                status="success",
                feed_results={},
            )
            report["artifacts"] = artifact_stats
            _save_run_report(dest_engine, report, {})
            print("\n" + json.dumps(report, indent=2, ensure_ascii=False))
            try:
                notify_pipeline_result(report)
            except Exception as notify_exc:
                print(f"  slack notify error: {notify_exc}", flush=True)
            return report
        except Exception as e:
            finished_at = _utc_now_naive()
            report = _build_report(
                started_at=started_at,
                finished_at=finished_at,
                status="failed",
                feed_results={},
                error_message=str(e),
            )
            try:
                _save_run_report(dest_engine, report, {})
            except Exception:
                pass
            try:
                notify_pipeline_result(report)
            except Exception as notify_exc:
                print(f"  slack notify error: {notify_exc}", flush=True)
            print(json.dumps(report, indent=2, ensure_ascii=False), file=sys.stderr)
            traceback.print_exc()
            raise

    src_engine = create_mysql_engine(os.environ["JOB_FEED_SOURCE_DATABASE_URL"])

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
        print("Job feed pipeline — incremental sync")
        print("=" * 60)
        print(f"Feeds: {', '.join(c.name for c in configs)}")
        if refresh_descriptions is True:
            print("Description refresh: ON (--refresh-descriptions)")
        else:
            print("Description refresh: OFF (default; pass --refresh-descriptions)")
        enriched: dict[int, str] = {}

        print("=" * 60)
        print("Purge archived job_postings from feed tables")
        print("=" * 60)
        with src_engine.connect() as src_conn, dest_engine.connect() as dest_conn:
            purged = purge_archived_job_postings_from_feeds(dest_conn, src_conn)
        print(f"  purge summary: {purged}", flush=True)

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

        artifact_stats: dict[str, dict] = {}
        if skip_artifacts:
            print("=" * 60)
            print("Skip feed XML artifacts (--skip-artifacts)")
            print("=" * 60)
        else:
            print("=" * 60)
            print("Generate feed XML artifacts (gzip)")
            if artifact_platforms:
                print(f"Platforms: {', '.join(sorted(artifact_platforms))}")
            print("=" * 60)
            artifact_stats = _generate_feed_xml_artifacts(
                dest_engine, platforms=artifact_platforms
            )
            for name, stats in artifact_stats.items():
                print(
                    f"  {name}: jobs={stats['job_count']} "
                    f"raw={stats['bytes_uncompressed']} gzip={stats['bytes_gzip']}"
                )
            print("=" * 60)
            print("Verify feed XML artifact integrity")
            print("=" * 60)
            _assert_artifact_integrity(dest_engine, platforms=artifact_platforms)

        finished_at = _utc_now_naive()
        report = _build_report(
            started_at=started_at,
            finished_at=finished_at,
            status="success",
            feed_results=feed_results,
        )
        if artifact_stats:
            report["artifacts"] = artifact_stats
        _save_run_report(dest_engine, report, feed_results)
        print("\n" + json.dumps(report, indent=2, ensure_ascii=False))
        try:
            notify_pipeline_result(report)
        except Exception as notify_exc:
            print(f"  slack notify error: {notify_exc}", flush=True)
        return report

    except Exception as e:
        finished_at = _utc_now_naive()
        partial = feed_results or {c.name: SyncResult(0, 0, 0, 0, 0) for c in configs}
        error_message = str(e)
        report = _build_report(
            started_at=started_at,
            finished_at=finished_at,
            status="failed",
            feed_results=partial,
            error_message=error_message,
        )
        try:
            _save_run_report(dest_engine, report, partial)
        except Exception:
            pass
        try:
            notify_pipeline_result(report)
        except Exception as notify_exc:
            print(f"  slack notify error: {notify_exc}", flush=True)
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
    parser.add_argument(
        "--artifacts-only",
        action="store_true",
        help="Skip feed sync; only regenerate gzip XML into feed_xml_artifact",
    )
    parser.add_argument(
        "--skip-artifacts",
        action="store_true",
        help="Sync feeds only; do not regenerate gzip XML artifacts",
    )
    args = parser.parse_args(argv)
    feed_names = [p for p in args.feeds.split(",") if p.strip()] or None
    run_pipeline(
        feed_names=feed_names,
        refresh_descriptions=True if args.refresh_descriptions else None,
        artifacts_only=bool(args.artifacts_only),
        skip_artifacts=bool(args.skip_artifacts),
    )


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(1)
