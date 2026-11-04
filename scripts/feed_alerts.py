"""Slack alerts + HTTP probes for job-feed pipeline / public XML endpoints."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.request import Request

from feed_buckets import FEEDS

DEFAULT_BASE_URL = "https://lw.joinrs.com"
DEFAULT_STALE_HOURS = 24
# Campaign feeds should never be empty once the catalog is synced.
DEFAULT_ARTIFACT_MIN_JOBS = 1
# Live XML without X-Feed-Job-Count: reject tiny / empty responses.
DEFAULT_LIVE_MIN_BYTES = 200

ARTIFACT_PLATFORMS = ("jooble", "talent", "adzuna")
LIVE_FEEDS: tuple[tuple[str, str], ...] = (
    ("whatjobs", "/wrapping/whatjobs"),
    ("hirematic", "/wrapping/hirematic"),
    ("jobrapido", "/wrapping/jobrapido"),
)

_SYNC_FEED_ORDER = (
    "jooble",
    "adzuna",
    "whatjobs",
    "hirematic",
    "jobrapido",
    "jooble_abroad",
)


@dataclass
class ProbeSpec:
    name: str
    path: str
    min_jobs: int = 0
    require_gzip: bool = False
    min_bytes: int = 0
    check_stale: bool = False


@dataclass
class ProbeResult:
    name: str
    path: str
    ok: bool
    http_status: int | None
    job_count: int | None
    content_encoding: str
    latency_ms: int
    error: str | None = None
    min_jobs: int = 0
    generated_at: str | None = None
    content_length: int | None = None


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def public_path_for_feed(platform: str, feed: str) -> str:
    """Map platform + feed key → public URL path (USA → /us/N)."""
    if feed.startswith("usa_"):
        shard = feed.split("_", 1)[1]
        return f"/wrapping/{platform}/us/{shard}"
    return f"/wrapping/{platform}/{feed}"


def build_probe_specs(
    *,
    include_live: bool = True,
    artifact_min_jobs: int | None = None,
    live_min_bytes: int | None = None,
) -> list[ProbeSpec]:
    """All partner endpoints that should stay healthy in production."""
    min_jobs = (
        DEFAULT_ARTIFACT_MIN_JOBS
        if artifact_min_jobs is None
        else artifact_min_jobs
    )
    min_bytes = DEFAULT_LIVE_MIN_BYTES if live_min_bytes is None else live_min_bytes
    specs: list[ProbeSpec] = []
    for platform in ARTIFACT_PLATFORMS:
        for feed in FEEDS:
            specs.append(
                ProbeSpec(
                    name=f"{platform}_{feed}",
                    path=public_path_for_feed(platform, feed),
                    min_jobs=min_jobs,
                    require_gzip=True,
                    check_stale=True,
                )
            )
    if include_live:
        for name, path in LIVE_FEEDS:
            specs.append(
                ProbeSpec(
                    name=name,
                    path=path,
                    min_jobs=0,
                    require_gzip=False,
                    min_bytes=min_bytes,
                    check_stale=False,
                )
            )
    return specs


def post_slack(
    text: str,
    *,
    webhook_url: str | None = None,
    blocks: list[dict[str, Any]] | None = None,
) -> bool:
    """POST mrkdwn text (optional Block Kit) to Slack Incoming Webhook. No-op if URL missing."""
    url = (webhook_url if webhook_url is not None else os.getenv("SLACK_WEBHOOK_URL") or "").strip()
    if not url:
        return False
    body: dict[str, Any] = {"text": text}
    if blocks:
        body["blocks"] = blocks
    payload = json.dumps(body).encode("utf-8")
    req = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        return True
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"  slack notify failed: {exc}", flush=True)
        return False


def _parse_generated_at(raw: str | None) -> datetime | None:
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def evaluate_probe(
    *,
    http_status: int | None,
    job_count: int | None,
    content_encoding: str,
    min_jobs: int,
    require_gzip: bool,
    content_length: int | None = None,
    min_bytes: int = 0,
    generated_at: str | None = None,
    stale_hours: int | None = None,
    now: datetime | None = None,
    check_stale: bool = False,
) -> tuple[bool, str | None]:
    """Return (ok, error_message). Pure helper for tests."""
    if http_status != 200:
        return False, f"http_status={http_status}"
    if require_gzip and "gzip" not in (content_encoding or "").lower():
        return False, f"expected gzip, got content-encoding={content_encoding!r}"
    if min_jobs > 0:
        if job_count is None:
            return False, "missing X-Feed-Job-Count"
        if job_count < min_jobs:
            return False, f"job_count={job_count} < min={min_jobs}"
    if min_bytes > 0 and content_length is not None and content_length < min_bytes:
        return False, f"content_length={content_length} < min={min_bytes}"
    if check_stale:
        max_age = DEFAULT_STALE_HOURS if stale_hours is None else stale_hours
        if max_age > 0:
            gen = _parse_generated_at(generated_at)
            if gen is None:
                return False, "missing/invalid X-Feed-Generated-At"
            ref = now or datetime.now(timezone.utc)
            age_h = (ref - gen.astimezone(timezone.utc)).total_seconds() / 3600.0
            if age_h > max_age:
                return False, f"stale artifact age_h={age_h:.1f} > {max_age}"
    return True, None


def probe_endpoint(
    name: str,
    path: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    min_jobs: int = 0,
    require_gzip: bool = False,
    min_bytes: int = 0,
    check_stale: bool = False,
    stale_hours: int | None = None,
    timeout: float = 45.0,
) -> ProbeResult:
    """GET endpoint; read headers + small body chunk, then close (no full download)."""
    url = base_url.rstrip("/") + path
    started = time.monotonic()
    try:
        req = Request(
            url,
            headers={
                "User-Agent": "joinrs-feed-health-probe/1.0",
                "Accept-Encoding": "identity",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = int(resp.getcode() or 0)
            encoding = (resp.headers.get("Content-Encoding") or "").lower()
            raw_count = resp.headers.get("X-Feed-Job-Count") or resp.headers.get(
                "x-feed-job-count"
            )
            generated_at = resp.headers.get("X-Feed-Generated-At") or resp.headers.get(
                "x-feed-generated-at"
            )
            raw_len = resp.headers.get("Content-Length")
            content_length: int | None
            try:
                content_length = int(raw_len) if raw_len not in (None, "") else None
            except ValueError:
                content_length = None
            try:
                job_count = (
                    int(raw_count)
                    if raw_count is not None and str(raw_count).strip() != ""
                    else None
                )
            except ValueError:
                job_count = None
            # Abort body early — campaign gzip feeds are tens of MB.
            resp.read(2048)
        latency_ms = int((time.monotonic() - started) * 1000)
        ok, err = evaluate_probe(
            http_status=status,
            job_count=job_count,
            content_encoding=encoding,
            min_jobs=min_jobs,
            require_gzip=require_gzip,
            content_length=content_length,
            min_bytes=min_bytes,
            generated_at=generated_at,
            stale_hours=stale_hours,
            check_stale=check_stale,
        )
        return ProbeResult(
            name=name,
            path=path,
            ok=ok,
            http_status=status,
            job_count=job_count,
            content_encoding=encoding,
            latency_ms=latency_ms,
            error=err,
            min_jobs=min_jobs,
            generated_at=generated_at,
            content_length=content_length,
        )
    except Exception as exc:  # noqa: BLE001 — surface as probe failure
        latency_ms = int((time.monotonic() - started) * 1000)
        return ProbeResult(
            name=name,
            path=path,
            ok=False,
            http_status=None,
            job_count=None,
            content_encoding="",
            latency_ms=latency_ms,
            error=str(exc),
            min_jobs=min_jobs,
        )


def probe_all_feeds(
    *,
    base_url: str | None = None,
    include_live: bool = True,
    timeout: float = 45.0,
    stale_hours: int | None = None,
) -> list[ProbeResult]:
    base = (base_url or os.getenv("FEED_PUBLIC_BASE_URL") or DEFAULT_BASE_URL).rstrip(
        "/"
    )
    max_age = (
        _env_int("FEED_STALE_HOURS", DEFAULT_STALE_HOURS)
        if stale_hours is None
        else stale_hours
    )
    results: list[ProbeResult] = []
    for spec in build_probe_specs(
        include_live=include_live,
    ):
        results.append(
            probe_endpoint(
                spec.name,
                spec.path,
                base_url=base,
                min_jobs=spec.min_jobs,
                require_gzip=spec.require_gzip,
                min_bytes=spec.min_bytes,
                check_stale=spec.check_stale,
                stale_hours=max_age,
                timeout=timeout,
            )
        )
    return results


def probes_ok(results: list[ProbeResult]) -> bool:
    return all(r.ok for r in results)


def probe_results_as_dicts(results: list[ProbeResult]) -> list[dict[str, Any]]:
    return [asdict(r) for r in results]


def _format_artifact_lines(artifacts: dict[str, Any]) -> list[str]:
    """Compact per-platform job counts (15 feeds)."""
    lines: list[str] = []
    for platform in ARTIFACT_PLATFORMS:
        parts: list[str] = []
        for feed in FEEDS:
            key = f"{platform}_{feed}"
            stats = artifacts.get(key)
            if not isinstance(stats, dict):
                continue
            short = feed if not feed.startswith("usa_") else feed.replace("usa_", "us")
            parts.append(f"{short}={stats.get('job_count', '?')}")
        if parts:
            lines.append(f"• `{platform}` " + " ".join(parts))
    known = {
        f"{platform}_{feed}"
        for platform in ARTIFACT_PLATFORMS
        for feed in FEEDS
    }
    extras = [k for k in artifacts if k not in known]
    for name in extras:
        stats = artifacts[name]
        if not isinstance(stats, dict):
            continue
        lines.append(
            f"• `{name}` jobs={stats.get('job_count', '?')} "
            f"gzip={stats.get('bytes_gzip', '?')}"
        )
    return lines


def format_pipeline_slack_message(
    report: dict[str, Any],
    *,
    probes: list[ProbeResult] | None = None,
) -> str:
    """Compact mrkdwn summary for Slack (always posted after Cron pipeline)."""
    status = report.get("status", "?")
    icon = {"success": ":white_check_mark:", "degraded": ":warning:", "failed": ":x:"}.get(
        status, ":grey_question:"
    )
    lines = [
        f"{icon} *Job feed pipeline* — `{status}`",
        f"duration: `{report.get('duration_sec', '?')}s` · "
        f"{report.get('started_at', '?')} → {report.get('finished_at', '?')}",
    ]
    if report.get("error_message"):
        lines.append(f"*error:* `{str(report['error_message'])[:500]}`")

    feeds = report.get("feeds") or {}
    if feeds:
        lines.append("*Sync (lw tables)*")
        ordered = [n for n in _SYNC_FEED_ORDER if n in feeds]
        ordered.extend(sorted(n for n in feeds if n not in _SYNC_FEED_ORDER))
        for name in ordered:
            row = feeds.get(name) or {}
            lines.append(
                f"• `{name}` total={row.get('total', 0)} "
                f"ins={row.get('inserted', 0)} del={row.get('deleted', 0)} "
                f"upd={row.get('updated', 0)} active={row.get('active', 0)}"
            )

    artifacts = report.get("artifacts") or {}
    if artifacts:
        lines.append("*Artifacts (gzip job_count)*")
        lines.extend(_format_artifact_lines(artifacts))

    probe_list = probes
    if probe_list is None and report.get("probes"):
        probe_list = [
            ProbeResult(**p) if isinstance(p, dict) else p for p in report["probes"]
        ]
    if probe_list:
        failed = [r for r in probe_list if not r.ok]
        lines.append(
            f"*HTTP probes* ok={len(probe_list) - len(failed)}/{len(probe_list)}"
        )
        show = failed if failed else probe_list[:5]
        for r in show:
            mark = "OK" if r.ok else "FAIL"
            count = r.job_count if r.job_count is not None else "-"
            extra = f" · {r.error}" if r.error else ""
            lines.append(
                f"• `{r.name}` [{mark}] http={r.http_status} "
                f"jobs={count} {r.latency_ms}ms{extra}"
            )
        if not failed and len(probe_list) > 5:
            lines.append(f"_… {len(probe_list) - 5} more OK_")

    return "\n".join(lines)


def format_health_slack_message(
    results: list[ProbeResult],
    *,
    base_url: str,
) -> str:
    """Alert-only message when one or more public endpoints look unhealthy."""
    failed = [r for r in results if not r.ok]
    ok_n = len(results) - len(failed)
    lines = [
        f":rotating_light: *Wrapping feed health* — `{len(failed)}` failing "
        f"({ok_n}/{len(results)} OK)",
        f"base: `{base_url}`",
    ]
    for r in failed:
        count = r.job_count if r.job_count is not None else "-"
        gen = r.generated_at or "-"
        lines.append(
            f"• `{r.name}` `{r.path}` http={r.http_status} jobs={count} "
            f"gen={gen} {r.latency_ms}ms · {r.error or 'unknown'}"
        )
    return "\n".join(lines)


def notify_pipeline_result(
    report: dict[str, Any],
    *,
    probes: list[ProbeResult] | None = None,
    webhook_url: str | None = None,
) -> bool:
    text = format_pipeline_slack_message(report, probes=probes)
    print("Slack message preview:\n" + text, flush=True)
    return post_slack(text, webhook_url=webhook_url)


def notify_health_failures(
    results: list[ProbeResult],
    *,
    base_url: str,
    webhook_url: str | None = None,
    quiet_success: bool = True,
) -> bool:
    """Post Slack only when probes fail (unless quiet_success=False)."""
    if probes_ok(results):
        if quiet_success:
            print(
                f"Feed health OK ({len(results)} endpoints) — Slack quiet",
                flush=True,
            )
            return False
        text = (
            f":white_check_mark: *Wrapping feed health* — all `{len(results)}` OK "
            f"({base_url})"
        )
        print("Slack message preview:\n" + text, flush=True)
        return post_slack(text, webhook_url=webhook_url)
    text = format_health_slack_message(results, base_url=base_url)
    print("Slack message preview:\n" + text, flush=True)
    return post_slack(text, webhook_url=webhook_url)


def check_db_artifact_integrity(
    *,
    database_url: str | None = None,
    gunzip: bool = True,
) -> list[dict[str, Any]]:
    """Inspect ``feed_xml_artifact`` for LENGTH/CRC mismatches (MySQL path)."""
    from job_feed_common import (
        campaign_artifact_feed_names,
        check_feed_xml_artifact_integrity,
        create_mysql_engine,
    )

    url = (database_url or os.getenv("DATABASE_URL") or "").strip()
    if not url:
        raise SystemExit("DATABASE_URL required for artifact integrity check")
    engine = create_mysql_engine(url)
    names = campaign_artifact_feed_names()
    with engine.connect() as conn:
        return check_feed_xml_artifact_integrity(
            conn, feed_names=names, gunzip=gunzip
        )


def format_artifact_integrity_slack_message(
    failures: list[dict[str, Any]],
) -> str:
    lines = [
        f":rotating_light: *Feed XML artifact integrity* — "
        f"`{len(failures)}` failing",
    ]
    for row in failures[:30]:
        name = row.get("feed_name", "?")
        err = row.get("error", "unknown")
        extra = ""
        if row.get("delta") is not None:
            extra = f" delta={row['delta']} plen={row.get('plen')} bgz={row.get('bytes_gzip')}"
        lines.append(f"• `{name}` {err}{extra}")
    if len(failures) > 30:
        lines.append(f"_… {len(failures) - 30} more_")
    return "\n".join(lines)


def notify_artifact_integrity_failures(
    failures: list[dict[str, Any]],
    *,
    webhook_url: str | None = None,
    quiet_success: bool = True,
) -> bool:
    if not failures:
        if quiet_success:
            print("Artifact integrity OK — Slack quiet", flush=True)
            return False
        text = ":white_check_mark: *Feed XML artifact integrity* — all OK"
        return post_slack(text, webhook_url=webhook_url)
    text = format_artifact_integrity_slack_message(failures)
    print("Slack message preview:\n" + text, flush=True)
    return post_slack(text, webhook_url=webhook_url)
