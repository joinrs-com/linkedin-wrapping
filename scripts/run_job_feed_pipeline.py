#!/usr/bin/env python3
"""
Pipeline incrementale feed job: sync export senza TRUNCATE (OpenAI enrichment skipped).

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
import gzip
import json
import os
import re
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


# Soft trim descriptions when a single campaign artifact would exceed MySQL packet limits
# (seen on jooble_usa ~118k jobs / ~890MB uncompressed / ~300MB gzip → connection reset).
# Server max_allowed_packet observed at 64MiB — keep gzip under this.
_ARTIFACT_LARGE_JOBS = 80_000
_ARTIFACT_MAX_DESCRIPTION_CHARS = 1_500
_ARTIFACT_RAW_SOFT_LIMIT = 200_000_000
_ARTIFACT_GZIP_HARD_LIMIT = 60_000_000
_DESC_CDATA_RE = re.compile(
    r"(<description><!\[CDATA\[)(.*?)(\]\]></description>)",
    re.DOTALL,
)


def _max_description_for_jobs(job_count: int) -> int | None:
    return _ARTIFACT_MAX_DESCRIPTION_CHARS if job_count >= _ARTIFACT_LARGE_JOBS else None


_FeedRowT = TypeVar("_FeedRowT", bound=SQLModel)
_ARTIFACT_LOAD_CHUNK = 2_000


def _bucket_where(model: type[SQLModel], bucket: str):
    """Match campaign bucket; NULL/empty bucket columns fold into 'row'."""
    if bucket == "row":
        return or_(model.bucket == "row", model.bucket.is_(None), model.bucket == "")  # type: ignore[attr-defined]
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


def _truncate_xml_descriptions(xml: str, max_chars: int) -> str:
    """Shrink already-built <description><![CDATA[…]]> bodies (abroad merge path)."""

    def _repl(match: re.Match[str]) -> str:
        body = match.group(2)
        if len(body) <= max_chars:
            return match.group(0)
        return f"{match.group(1)}{body[:max_chars]}{match.group(3)}"

    return _DESC_CDATA_RE.sub(_repl, xml)


def _extract_job_blocks(source_xml: str) -> str:
    parts: list[str] = []
    start = 0
    while True:
        i = source_xml.find("<job>", start)
        if i < 0:
            break
        j = source_xml.find("</job>", i)
        if j < 0:
            break
        parts.append(source_xml[i : j + len("</job>")])
        start = j + len("</job>")
    return "\n".join(parts)


def _wrap_jooble_source_xml(job_blocks: str) -> str:
    last_build = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<source>\n"
        f" <lastBuildDate> {last_build} </lastBuildDate>\n"
        f"{job_blocks}\n"
        "</source>"
    )


def _upsert_abroad_from_bucket_artifacts(dest_conn, stats: dict[str, dict]) -> dict:
    """Build jooble_abroad by merging jooble_{usa,eu3,row} payloads (no row reload).

    Avoids a second multi-hour SELECT of ~340k rows; shrinks descriptions until gzip
    fits under server max_allowed_packet (~64MiB).
    """
    bucket_names = [artifact_name("jooble", b) for b in ("usa", "eu3", "row")]
    sources: list[str] = []
    total_jobs = 0
    for name in bucket_names:
        row = dest_conn.execute(
            text(
                "SELECT payload, job_count FROM feed_xml_artifact WHERE feed_name = :n"
            ),
            {"n": name},
        ).mappings().first()
        if row is None:
            raise RuntimeError(f"missing bucket artifact {name} for jooble_abroad merge")
        xml = gzip.decompress(bytes(row["payload"])).decode("utf-8")
        sources.append(xml)
        total_jobs += int(row["job_count"] or 0)
        print(
            f"  abroad merge source {name}: jobs={row['job_count']} "
            f"xml_bytes={len(xml)}",
            flush=True,
        )

    max_desc = 500
    while True:
        print(
            f"  soft-trim abroad merge descriptions to {max_desc} chars "
            f"({total_jobs} jobs)",
            flush=True,
        )
        job_blocks = "\n".join(
            _extract_job_blocks(_truncate_xml_descriptions(xml, max_desc))
            for xml in sources
        )
        xml_text = _wrap_jooble_source_xml(job_blocks)
        raw_len = len(xml_text.encode("utf-8"))
        gz_probe = len(gzip.compress(xml_text.encode("utf-8"), compresslevel=9))
        if gz_probe > _ARTIFACT_GZIP_HARD_LIMIT and max_desc > 100:
            next_desc = max(100, max_desc // 2)
            print(
                f"  artifact jooble_abroad: raw={raw_len} gzip~={gz_probe} still large; "
                f"tightening trim {max_desc} → {next_desc}",
                flush=True,
            )
            del xml_text, job_blocks
            max_desc = next_desc
            continue
        try:
            result = upsert_feed_xml_artifact(
                dest_conn,
                feed_name="jooble_abroad",
                xml_text=xml_text,
                job_count=total_jobs,
            )
            stats["jooble_abroad"] = result
            return result
        finally:
            del xml_text, job_blocks


def _upsert_xml_artifact(
    dest_conn,
    *,
    feed_name: str,
    rows: list,
    job_count: int,
    builder,
) -> dict:
    """Generate XML (with adaptive soft-trim) and UPSERT; free the string ASAP."""
    max_desc = _max_description_for_jobs(job_count)
    while True:
        if max_desc:
            print(
                f"  soft-trim descriptions to {max_desc} chars for {feed_name} "
                f"({job_count} jobs)",
                flush=True,
            )
        xml_text = builder(rows, max_desc)
        raw_len = len(xml_text.encode("utf-8"))
        gz_probe = len(gzip.compress(xml_text.encode("utf-8"), compresslevel=9))
        needs_tighten = (
            (
                raw_len > _ARTIFACT_RAW_SOFT_LIMIT
                and job_count >= _ARTIFACT_LARGE_JOBS
            )
            or gz_probe > _ARTIFACT_GZIP_HARD_LIMIT
        ) and (max_desc is None or max_desc > 100)
        if needs_tighten:
            next_desc = 500 if max_desc is None else max(100, max_desc // 2)
            print(
                f"  artifact {feed_name}: raw={raw_len} gzip~={gz_probe} still large; "
                f"tightening trim {max_desc} → {next_desc}",
                flush=True,
            )
            del xml_text
            max_desc = next_desc
            continue
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
    """Build gzip XML per platform × campaign bucket (+ legacy root aliases).

    Loads one bucket at a time (chunked) so ~345k-row full-table SELECTs do not
    hit MySQL lost-connection mid-result.
    platforms: optional subset of {"jooble","talent","adzuna"}; None = all.
    """
    want = platforms or {"jooble", "talent", "adzuna"}
    stats: dict[str, dict] = {}

    def _jooble_xml(rows: list, max_desc: int | None) -> str:
        return generate_wrapping_xml(
            rows,
            apply_url_mode="jooble",
            prefer_employers_name_as_company=True,
            include_priority=True,
            include_employers_id=True,
            include_country_code=True,
            max_description_chars=max_desc,
        )

    def _talent_xml(rows: list, max_desc: int | None) -> str:
        return generate_wrapping_xml(
            rows,
            apply_url_mode="jooble",
            prefer_employers_name_as_company=True,
            include_priority=True,
            include_employers_id=True,
            include_country_code=True,
            description_sanitizer=normalize_description_for_talent,
            max_description_chars=max_desc,
        )

    def _adzuna_xml(rows: list, max_desc: int | None) -> str:
        return generate_adzuna_xml(rows, max_description_chars=max_desc)

    with dest_engine.connect() as dest_conn:
        for bucket in BUCKETS:
            print(f"\n-- artifacts for bucket={bucket} --", flush=True)
            if "jooble" in want or "talent" in want:
                j_rows = _load_feed_bucket(dest_engine, JoobleJobFeed, bucket)
                if "jooble" in want:
                    stats[artifact_name("jooble", bucket)] = _upsert_xml_artifact(
                        dest_conn,
                        feed_name=artifact_name("jooble", bucket),
                        rows=j_rows,
                        job_count=len(j_rows),
                        builder=_jooble_xml,
                    )
                if "talent" in want:
                    stats[artifact_name("talent", bucket)] = _upsert_xml_artifact(
                        dest_conn,
                        feed_name=artifact_name("talent", bucket),
                        rows=j_rows,
                        job_count=len(j_rows),
                        builder=_talent_xml,
                    )
                del j_rows
                gc.collect()

            if "adzuna" in want:
                a_rows = _load_feed_bucket(dest_engine, AdzunaJobFeed, bucket)
                stats[artifact_name("adzuna", bucket)] = _upsert_xml_artifact(
                    dest_conn,
                    feed_name=artifact_name("adzuna", bucket),
                    rows=a_rows,
                    job_count=len(a_rows),
                    builder=_adzuna_xml,
                )
                del a_rows
                gc.collect()

        # Compat: /wrapping/jooble|talent|adzuna still resolve artifact keys without suffix
        for platform in ("jooble", "talent", "adzuna"):
            if platform not in want:
                continue
            src = artifact_name(platform, "ita_esp")
            if src in stats:
                legacy = legacy_root_artifact_name(platform)
                # Re-use already-uploaded ita_esp payload via a lightweight SQL copy.
                dest_conn.execute(
                    text(
                        """
                        INSERT INTO feed_xml_artifact
                            (feed_name, payload, content_type, job_count, bytes_uncompressed, generated_at)
                        SELECT :legacy, payload, content_type, job_count, bytes_uncompressed, generated_at
                        FROM feed_xml_artifact
                        WHERE feed_name = :src
                        ON DUPLICATE KEY UPDATE
                            payload = VALUES(payload),
                            content_type = VALUES(content_type),
                            job_count = VALUES(job_count),
                            bytes_uncompressed = VALUES(bytes_uncompressed),
                            generated_at = VALUES(generated_at)
                        """
                    ),
                    {"legacy": legacy, "src": src},
                )
                dest_conn.commit()
                stats[legacy] = {**stats[src], "feed_name": legacy}

        # Compat: /wrapping/jooble/abroad → usa∪eu3∪row (deprecated; prefer /us /eu3 /row)
        if "jooble" in want:
            print("\n-- artifacts for jooble_abroad (usa∪eu3∪row merge) --", flush=True)
            _upsert_abroad_from_bucket_artifacts(dest_conn, stats)
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
    dest_engine = ijd.create_database_engine()
    enrichment = ijd.EnrichmentResult(processed=0, deleted=0, total=0, eligible_active=0)
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
            finished_at = _utc_now_naive()
            report = _build_report(
                started_at=started_at,
                finished_at=finished_at,
                status="success",
                enrichment=enrichment,
                feed_results={},
            )
            report["artifacts"] = artifact_stats
            _save_run_report(dest_engine, report, enrichment, {})
            print("\n" + json.dumps(report, indent=2, ensure_ascii=False))
            return report
        except Exception as e:
            finished_at = _utc_now_naive()
            report = _build_report(
                started_at=started_at,
                finished_at=finished_at,
                status="failed",
                enrichment=enrichment,
                feed_results={},
                error_message=str(e),
            )
            try:
                _save_run_report(dest_engine, report, enrichment, {})
            except Exception:
                pass
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

        finished_at = _utc_now_naive()
        report = _build_report(
            started_at=started_at,
            finished_at=finished_at,
            status="success",
            enrichment=enrichment,
            feed_results=feed_results,
        )
        if artifact_stats:
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
