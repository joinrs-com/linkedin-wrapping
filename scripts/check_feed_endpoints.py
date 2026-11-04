#!/usr/bin/env python3
"""Probe public /wrapping/* partner URLs and Slack-alert on failures.

Designed for a lightweight K8s CronJob (quiet success). Uses production base URL
so checks match what partners see (default https://lw.joinrs.com).

Env:
  SLACK_WEBHOOK_URL      optional Incoming Webhook
  FEED_PUBLIC_BASE_URL   default https://lw.joinrs.com
  FEED_STALE_HOURS       max age for X-Feed-Generated-At (default 24)
  FEED_HEALTH_QUIET=0    also post Slack on all-OK

Usage:
  python scripts/check_feed_endpoints.py
  python scripts/check_feed_endpoints.py --base-url https://lw.joinrs.com --verbose
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "scripts"))

_env_file = project_root / ".env"
if _env_file.is_file():
    load_dotenv(_env_file, override=True)

from feed_alerts import (  # noqa: E402
    DEFAULT_BASE_URL,
    check_db_artifact_integrity,
    notify_artifact_integrity_failures,
    notify_health_failures,
    probe_all_feeds,
    probes_ok,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HTTP health probe for wrapping feeds")
    parser.add_argument(
        "--base-url",
        default="",
        help="Public base URL (default FEED_PUBLIC_BASE_URL or https://lw.joinrs.com)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=45.0,
        help="Per-endpoint timeout seconds (default 45)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print every probe result",
    )
    parser.add_argument(
        "--notify-success",
        action="store_true",
        help="Also post Slack when all probes pass",
    )
    parser.add_argument(
        "--skip-db-integrity",
        action="store_true",
        help="Skip MySQL feed_xml_artifact LENGTH/CRC check (needs DATABASE_URL)",
    )
    args = parser.parse_args(argv)

    base = (
        args.base_url.strip()
        or os.getenv("FEED_PUBLIC_BASE_URL")
        or DEFAULT_BASE_URL
    ).rstrip("/")
    quiet = not args.notify_success and (
        (os.getenv("FEED_HEALTH_QUIET") or "1").strip() != "0"
    )

    integrity_failed = False
    if not args.skip_db_integrity and (os.getenv("DATABASE_URL") or "").strip():
        print("Checking feed_xml_artifact integrity (MySQL) …", flush=True)
        try:
            failures = check_db_artifact_integrity(gunzip=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  integrity check error: {exc}", flush=True)
            failures = [{"feed_name": "?", "error": str(exc)}]
        if failures:
            integrity_failed = True
            for row in failures:
                print(
                    f"  FAIL {row.get('feed_name')}: {row.get('error')} "
                    f"delta={row.get('delta')}",
                    flush=True,
                )
        else:
            print("  artifact integrity OK", flush=True)
        notify_artifact_integrity_failures(
            failures, quiet_success=quiet
        )
    elif not args.skip_db_integrity:
        print(
            "Skip DB integrity (DATABASE_URL unset); HTTP probes only",
            flush=True,
        )

    print(f"Probing wrapping feeds at {base} …", flush=True)
    results = probe_all_feeds(base_url=base, timeout=args.timeout)
    failed = [r for r in results if not r.ok]
    for r in results:
        if args.verbose or not r.ok:
            mark = "OK" if r.ok else "FAIL"
            print(
                f"  [{mark}] {r.name} {r.path} http={r.http_status} "
                f"jobs={r.job_count} gen={r.generated_at or '-'} "
                f"{r.latency_ms}ms"
                + (f" err={r.error}" if r.error else ""),
                flush=True,
            )
    print(
        f"Summary: {len(results) - len(failed)}/{len(results)} OK, "
        f"{len(failed)} FAIL",
        flush=True,
    )

    try:
        notify_health_failures(
            results,
            base_url=base,
            quiet_success=quiet,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  slack notify error: {exc}", flush=True)

    ok = probes_ok(results) and not integrity_failed
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
