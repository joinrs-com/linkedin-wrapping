#!/usr/bin/env python3
"""Poll jooble/adzuna row counts + last pipeline run (visible monitoring).

Usage:
    set -a && source .env && set +a
    python scripts/watch_job_feed_progress.py
    python scripts/watch_job_feed_progress.py --once
    python scripts/watch_job_feed_progress.py --interval 30
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "scripts"))

_env_file = project_root / ".env"
if _env_file.is_file():
    load_dotenv(_env_file, override=True)

import improve_job_descriptions as ijd  # noqa: E402


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _snapshot(engine) -> None:
    lines: list[str] = [f"=== job feed progress @ {_utc_now()} ==="]
    with engine.connect() as conn:
        for table in ("jooble_job_feed", "adzuna_job_feed"):
            try:
                total = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                lines.append(f"{table}: total={total}")
                rows = conn.execute(
                    text(
                        f"SELECT bucket, COUNT(*) AS n FROM {table} "
                        f"GROUP BY bucket ORDER BY bucket"
                    )
                ).fetchall()
                for bucket, n in rows:
                    lines.append(f"  bucket={bucket!s}: {n}")
            except Exception as exc:  # noqa: BLE001 — monitoring must not crash
                lines.append(f"{table}: ERROR {exc}")

        try:
            run = conn.execute(
                text(
                    "SELECT id, status, started_at, finished_at, duration_sec, "
                    "error_message FROM job_feed_pipeline_run "
                    "ORDER BY id DESC LIMIT 1"
                )
            ).mappings().first()
            if run:
                err = (run["error_message"] or "")[:180]
                lines.append(
                    f"last run id={run['id']} status={run['status']} "
                    f"started={run['started_at']} finished={run['finished_at']} "
                    f"duration_sec={run['duration_sec']}"
                )
                if err:
                    lines.append(f"  error: {err}")
            else:
                lines.append("last run: (none)")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"job_feed_pipeline_run: ERROR {exc}")

    print("\n".join(lines), flush=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Watch job feed sync progress")
    parser.add_argument("--once", action="store_true", help="Print one snapshot and exit")
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Seconds between snapshots (default 60)",
    )
    args = parser.parse_args(argv)

    if not os.getenv("DATABASE_URL"):
        raise SystemExit("DATABASE_URL non impostata")

    engine = ijd.create_database_engine()
    if args.once:
        _snapshot(engine)
        return

    print(
        f"Watching every {args.interval}s (Ctrl+C to stop). "
        "Also: kubectl logs -f job/<job-feed-manual-…> -n lw",
        flush=True,
    )
    try:
        while True:
            _snapshot(engine)
            time.sleep(max(5, args.interval))
    except KeyboardInterrupt:
        print("\nstopped", flush=True)


if __name__ == "__main__":
    main()
