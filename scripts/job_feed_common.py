"""Shared helpers for incremental job feed sync (production → lw)."""

from __future__ import annotations

import gzip
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError, OperationalError

# Jooble/Adzuna full-catalog SELECT ships description on every explode row.
# Phase-1 slim replaces that expression so id/meta sync stays light.
_DESCRIPTION_SELECT_RE = re.compile(
    r"CONCAT\(\s*'<p>',\s*n\.description,\s*'</p>'\s*\)\s+AS\s+description",
    re.IGNORECASE,
)


@dataclass
class SyncResult:
    active: int
    inserted: int
    deleted: int
    unchanged: int
    total: int
    updated: int = 0


def mysql_identifier(name: str) -> str:
    if not name or not name.replace("_", "").isalnum():
        raise ValueError(f"Identificatore MySQL non valido: {name!r}")
    return name


def apply_job_feed_db_qualifiers(sql: str) -> str:
    jp = mysql_identifier(os.getenv("JOB_FEED_DB_JOB_POSTINGS", "job_postings"))
    em = mysql_identifier(os.getenv("JOB_FEED_DB_EMPLOYERS", "employers"))
    sql = sql.replace("job_postings.job_postings_1", f"{jp}.job_postings_1")
    sql = sql.replace("employers.employers", f"{em}.employers")
    return sql


def load_sql(project_root: Path, filename: str) -> str:
    path = project_root / "scripts" / "sql" / filename
    if not path.is_file():
        raise FileNotFoundError(f"File SQL mancante: {path}")
    # Literal % (DATE_FORMAT / LIKE) is fine with text(): SQLAlchemy escapes
    # for pyformat on compile; do not pre-double or DATE_FORMAT breaks.
    return apply_job_feed_db_qualifiers(path.read_text(encoding="utf-8"))


def slim_feed_select_sql(select_sql: str) -> str:
    """Drop description body from a full-catalog feed SELECT (NULL placeholder)."""
    slim, n = _DESCRIPTION_SELECT_RE.subn(
        "CAST(NULL AS CHAR) AS description", select_sql, count=1
    )
    if n != 1:
        raise ValueError(
            "slim_feed_select_sql: expected exactly one "
            "CONCAT('<p>', n.description, '</p>') AS description expression"
        )
    return slim


def _fetch_job_descriptions(
    source_conn: Connection,
    job_posting_ids: list[int],
    *,
    chunk_size: int = 200,
) -> dict[int, str]:
    """Load CONCAT('<p>', description, '</p>') for distinct job_posting ids."""
    if not job_posting_ids:
        return {}
    jp = mysql_identifier(os.getenv("JOB_FEED_DB_JOB_POSTINGS", "job_postings"))
    table = f"{jp}.job_postings_1"
    out: dict[int, str] = {}
    unique_ids = sorted({int(j) for j in job_posting_ids})
    total = len(unique_ids)
    print(
        f"  description fetch: {total} unique job_posting_id (chunk={chunk_size})…",
        flush=True,
    )
    done = 0
    for chunk in _chunked(unique_ids, chunk_size):
        placeholders = ", ".join(f":id{i}" for i in range(len(chunk)))
        params = {f"id{i}": v for i, v in enumerate(chunk)}
        rows = source_conn.execute(
            text(
                f"SELECT id, CONCAT('<p>', description, '</p>') AS description "
                f"FROM {table} WHERE id IN ({placeholders})"
            ),
            params,
        ).fetchall()
        for r in rows:
            out[int(r[0])] = r[1]
        done += len(chunk)
        if done % 2000 < chunk_size or done == total:
            print(f"  description fetch progress: {done}/{total}", flush=True)
    return out


def create_mysql_engine(url: str) -> Engine:
    # Long feed syncs (normalize + multi-row INSERT) need generous I/O timeouts;
    # pool_pre_ping recovers stale pooled connections between chunks.
    eng = create_engine(
        url,
        pool_recycle=1800,
        pool_pre_ping=True,
        echo=False,
        connect_args={
            "connect_timeout": 60,
            "read_timeout": 1800,
            "write_timeout": 1800,
        },
    )
    if eng.dialect.name != "mysql":
        raise ValueError(f"Atteso MySQL, trovato {eng.dialect.name}")
    return eng


def _is_transient_db_error(exc: BaseException) -> bool:
    """True for MySQL disconnect / timeout that is safe to retry."""
    if isinstance(exc, (TimeoutError, BrokenPipeError, ConnectionResetError)):
        return True
    parts: list[BaseException] = [exc]
    orig = getattr(exc, "orig", None)
    if isinstance(orig, BaseException):
        parts.append(orig)
    cause = exc.__cause__
    if isinstance(cause, BaseException) and cause not in parts:
        parts.append(cause)
    codes: set[int] = set()
    msgs: list[str] = []
    for part in parts:
        if isinstance(part, (TimeoutError, BrokenPipeError, ConnectionResetError)):
            return True
        msgs.append(str(part).lower())
        args = getattr(part, "args", ())
        if args and isinstance(args[0], int):
            codes.add(args[0])
    # 2006/2013 gone-away; 2003 connect timeout; 1205 lock wait; 4031 idle kill
    if codes & {2003, 2006, 2013, 2014, 1205, 4031}:
        return True
    blob = " ".join(msgs)
    return any(
        s in blob
        for s in (
            "lost connection",
            "server has gone away",
            "timed out",
            "connection reset",
            "broken pipe",
            "lock wait timeout",
            "can't connect",
            "cannot connect",
            "errno 60",
            "errno 54",
            "errno 49",
            "errno 8",
            "can't assign requested address",
            "nodename nor servname",
            "name or service not known",
        )
    )


def load_enriched_descriptions(conn: Connection) -> dict[int, str]:
    rows = conn.execute(text("SELECT job_id, description FROM job_description_enriched")).fetchall()
    return {int(r[0]): r[1] for r in rows}


def _normalize_id(value: Any, *, as_string: bool) -> str | int:
    if value is None:
        raise ValueError("id nullo nella riga sorgente")
    if as_string:
        return str(value)
    return int(value)


def _job_id_from_row(row: dict[str, Any], id_column: str) -> int:
    """Resolve numeric job posting id for enrichment lookup.

    Prefer explicit ``job_posting_id`` when present (e.g. Job Rapido explode rows
    whose primary key is ``reference_id``).
    """
    if row.get("job_posting_id") is not None:
        return int(row["job_posting_id"])
    return int(row[id_column])


def _chunked(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


class _ReusableDbConn:
    """One long-lived Connection for a multi-chunk call; invalidate+reconnect on transient errors.

    Pass an Engine to own the socket (preferred after long idle work). Pass a
    Connection to reuse it (tests / callers that already hold one) unless a
    retry forces reconnect via the engine.
    """

    def __init__(self, conn_or_engine: Connection | Engine):
        self.engine: Engine = (
            conn_or_engine
            if isinstance(conn_or_engine, Engine)
            else conn_or_engine.engine
        )
        self.owns_conn = isinstance(conn_or_engine, Engine)
        self.conn: Connection = (
            self.engine.connect()
            if self.owns_conn
            else conn_or_engine  # type: ignore[assignment]
        )

    def reconnect(self) -> Connection:
        try:
            self.conn.rollback()
        except Exception:
            pass
        try:
            self.conn.invalidate()
        except Exception:
            pass
        try:
            if self.owns_conn:
                self.conn.close()
        except Exception:
            pass
        self.conn = self.engine.connect()
        self.owns_conn = True
        return self.conn

    def close(self) -> None:
        if self.owns_conn:
            try:
                self.conn.close()
            except Exception:
                pass

    def run_chunk(
        self,
        fn,
        *,
        max_retries: int = 6,
        label: str = "db",
    ):
        """Execute ``fn(conn)``; retry the same chunk after transient disconnect."""
        last_exc: BaseException | None = None
        for attempt in range(max_retries):
            try:
                return fn(self.conn)
            except (OperationalError, DBAPIError, TimeoutError, OSError) as exc:
                last_exc = exc
                if not _is_transient_db_error(exc) or attempt + 1 >= max_retries:
                    raise
                wait = min(60.0, 2.0**attempt)
                # Truncate: SQLAlchemy OperationalError embeds full SQL+params.
                exc_short = str(exc).split("[SQL:", 1)[0].strip() or str(exc)[:200]
                print(
                    f"  {label} retry {attempt + 1}/{max_retries - 1} "
                    f"after transient error ({wait:.0f}s): {exc_short}",
                    flush=True,
                )
                time.sleep(wait)
                try:
                    self.reconnect()
                except (OperationalError, DBAPIError, TimeoutError, OSError) as reconn_exc:
                    last_exc = reconn_exc
                    if not _is_transient_db_error(reconn_exc):
                        raise
                    # Ephemeral-port / DNS blips: keep retrying the chunk.
                    reconn_short = (
                        str(reconn_exc).split("[SQL:", 1)[0].strip()
                        or str(reconn_exc)[:200]
                    )
                    print(
                        f"  {label} reconnect failed ({reconn_short}); "
                        f"will retry chunk",
                        flush=True,
                    )
                    time.sleep(min(60.0, 2.0 ** (attempt + 1)))
                    try:
                        self.reconnect()
                    except (OperationalError, DBAPIError, TimeoutError, OSError):
                        # Next loop iteration will fail on fn(conn) and retry again.
                        pass
        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"{label}: unexpected empty retry loop")


def _delete_ids(conn: Connection, table: str, id_column: str, ids: list, *, chunk_size: int = 500) -> int:
    if not ids:
        return 0
    deleted = 0
    for chunk in _chunked(ids, chunk_size):
        placeholders = ", ".join(f":id{i}" for i in range(len(chunk)))
        params = {f"id{i}": v for i, v in enumerate(chunk)}
        conn.execute(
            text(f"DELETE FROM {table} WHERE {id_column} IN ({placeholders})"),
            params,
        )
        deleted += len(chunk)
    return deleted


def _insert_rows(
    conn_or_engine: Connection | Engine,
    table: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    *,
    chunk_size: int = 5,
    max_retries: int = 6,
    progress_every: int = 0,
) -> int:
    """Multi-row INSERT in chunks; commit each chunk to avoid long transactions.

    Reuses one long-lived Connection for the whole call (no per-chunk
    ``engine.begin()`` — that exhausted ephemeral ports on large syncs).
    On transient MySQL errors, invalidate + reconnect once then retry the
    same chunk. INSERT IGNORE makes retries idempotent.
    Set progress_every>0 to log every N rows within this call.
    """
    if not rows:
        return 0
    dialect_name = (
        conn_or_engine.dialect.name
        if isinstance(conn_or_engine, Engine)
        else conn_or_engine.engine.dialect.name
    )
    col_sql = ", ".join(columns)
    # MySQL: INSERT IGNORE; SQLite (tests): INSERT OR IGNORE
    insert_kw = "INSERT IGNORE" if dialect_name == "mysql" else "INSERT OR IGNORE"

    db = _ReusableDbConn(conn_or_engine)
    inserted = 0
    done = 0
    total = len(rows)
    try:
        for chunk in _chunked(rows, chunk_size):
            value_groups: list[str] = []
            payload: dict[str, Any] = {}
            for i, row in enumerate(chunk):
                value_groups.append(
                    "(" + ", ".join(f":{c}_{i}" for c in columns) + ")"
                )
                for c in columns:
                    payload[f"{c}_{i}"] = row.get(c)
            stmt = text(
                f"{insert_kw} INTO {table} ({col_sql}) VALUES {', '.join(value_groups)}"
            )

            def _do(conn: Connection, _stmt=stmt, _payload=payload) -> int:
                result = conn.execute(_stmt, _payload)
                conn.commit()
                return max(int(result.rowcount or 0), 0)

            inserted += db.run_chunk(_do, max_retries=max_retries, label="insert")
            done += len(chunk)
            if progress_every and (
                done % progress_every < chunk_size or done == total
            ):
                print(
                    f"  insert progress: {done}/{total} (written≈{inserted})",
                    flush=True,
                )
    finally:
        db.close()
    return inserted


def _prepare_row_payload(
    row: dict[str, Any],
    *,
    columns: list[str],
    id_column: str,
    description_column: str | None,
    enriched: dict[int, str],
    normalize_html: bool,
    talent_normalize,
    norm_cache: dict[int, str] | None = None,
) -> dict[str, Any]:
    """Build insert/update payload; optionally HTML-normalize description (+ talent).

    When ``norm_cache`` is provided, HTML normalize runs once per ``job_posting_id``
    (explode rows of the same job share the description).
    """
    row = dict(row)
    if description_column and enriched:
        job_id = _job_id_from_row(row, id_column)
        if job_id in enriched:
            row[description_column] = enriched[job_id]
    payload = {c: row.get(c) for c in columns}
    if normalize_html and description_column and talent_normalize is not None:
        jid: int | None = None
        if row.get("job_posting_id") is not None:
            jid = int(row["job_posting_id"])
        if norm_cache is not None and jid is not None and jid in norm_cache:
            norm = norm_cache[jid]
        else:
            norm = talent_normalize(payload.get(description_column))
            if norm_cache is not None and jid is not None:
                norm_cache[jid] = norm
        payload[description_column] = norm
        if "description_talent" in columns:
            payload["description_talent"] = norm
    elif "description_talent" in columns and description_column and talent_normalize is not None:
        if payload.get("description_talent") is None:
            jid = int(row["job_posting_id"]) if row.get("job_posting_id") is not None else None
            if norm_cache is not None and jid is not None and jid in norm_cache:
                payload["description_talent"] = norm_cache[jid]
            else:
                norm = talent_normalize(payload.get(description_column))
                if norm_cache is not None and jid is not None:
                    norm_cache[jid] = norm
                payload["description_talent"] = norm
    return payload


def _update_descriptions_by_job_posting_id(
    conn_or_engine: Connection | Engine,
    table: str,
    description_column: str,
    jobs: list[dict[str, Any]],
    *,
    also_talent: bool = False,
    chunk_size: int = 100,
    max_retries: int = 6,
) -> int:
    """UPDATE description for all explode rows of each job_posting_id (one stmt per job)."""
    if not jobs:
        return 0
    db = _ReusableDbConn(conn_or_engine)
    updated_jobs = 0
    total = len(jobs)
    try:
        for chunk in _chunked(jobs, chunk_size):
            if also_talent:
                stmt = text(
                    f"UPDATE {table} SET {description_column} = :d, description_talent = :dt "
                    f"WHERE job_posting_id = :jid"
                )
                payload = [
                    {
                        "jid": j["job_posting_id"],
                        "d": j[description_column],
                        "dt": j.get("description_talent"),
                    }
                    for j in chunk
                ]
            else:
                stmt = text(
                    f"UPDATE {table} SET {description_column} = :d WHERE job_posting_id = :jid"
                )
                payload = [
                    {"jid": j["job_posting_id"], "d": j[description_column]} for j in chunk
                ]

            def _do(conn: Connection, _stmt=stmt, _payload=payload) -> None:
                conn.execute(_stmt, _payload)
                conn.commit()

            db.run_chunk(_do, max_retries=max_retries, label="description update")
            updated_jobs += len(chunk)
            if updated_jobs % 5000 == 0 or updated_jobs == total:
                print(
                    f"  description refresh progress: {updated_jobs}/{total} jobs",
                    flush=True,
                )
    finally:
        db.close()
    return updated_jobs


def _load_existing_descriptions(
    conn_or_engine: Connection | Engine,
    table: str,
    id_column: str,
    description_column: str,
    ids: list,
    *,
    string_id: bool = False,
    also_talent: bool = False,
    chunk_size: int = 200,
    max_retries: int = 6,
    progress_every: int = 20000,
) -> dict[Any, dict[str, Any]]:
    """Map id → current description (+ optional description_talent) on dest.

    Reuses one Connection across IN chunks; retries on transient MySQL errors.
    Smaller default chunk_size keeps SELECT result sets bounded (large TEXT).
    """
    if not ids:
        return {}
    cols = f"{id_column}, {description_column}"
    if also_talent:
        cols += ", description_talent"
    id_list = list(ids)
    total = len(id_list)
    print(
        f"  description refresh: loading existing for {total} ids "
        f"(chunk={chunk_size})…",
        flush=True,
    )
    db = _ReusableDbConn(conn_or_engine)
    out: dict[Any, dict[str, Any]] = {}
    done = 0
    try:
        for chunk in _chunked(id_list, chunk_size):
            placeholders = ", ".join(f":id{i}" for i in range(len(chunk)))
            params = {f"id{i}": v for i, v in enumerate(chunk)}
            stmt = text(
                f"SELECT {cols} FROM {table} WHERE {id_column} IN ({placeholders})"
            )

            def _do(conn: Connection, _stmt=stmt, _params=params):
                return conn.execute(_stmt, _params).fetchall()

            rows = db.run_chunk(_do, max_retries=max_retries, label="description load")
            for r in rows:
                entry = {description_column: r[1]}
                if also_talent:
                    entry["description_talent"] = r[2]
                out[_normalize_id(r[0], as_string=string_id)] = entry
            done += len(chunk)
            if progress_every and (
                done % progress_every < chunk_size or done == total
            ):
                print(
                    f"  description load progress: {done}/{total}",
                    flush=True,
                )
    finally:
        db.close()
    return out


def _filter_stale_description_rows(
    rows: list[dict[str, Any]],
    existing: dict[Any, dict[str, Any]],
    description_column: str,
    *,
    also_talent: bool = False,
) -> list[dict[str, Any]]:
    """Keep only rows whose dest description differs from the new payload (resume-safe)."""
    stale: list[dict[str, Any]] = []
    for r in rows:
        cur = existing.get(r["id"])
        if cur is None:
            stale.append(r)
            continue
        if cur.get(description_column) != r.get(description_column):
            stale.append(r)
            continue
        if also_talent and cur.get("description_talent") != r.get("description_talent"):
            stale.append(r)
            continue
    return stale


def _update_description_rows(
    conn_or_engine: Connection | Engine,
    table: str,
    id_column: str,
    description_column: str,
    rows: list[dict[str, Any]],
    *,
    also_talent: bool = False,
    chunk_size: int = 100,
    max_retries: int = 6,
) -> int:
    """UPDATE description (+ optional description_talent) for existing feed rows."""
    if not rows:
        return 0
    db = _ReusableDbConn(conn_or_engine)
    updated = 0
    total = len(rows)
    try:
        for chunk in _chunked(rows, chunk_size):
            if also_talent:
                stmt = text(
                    f"UPDATE {table} SET {description_column} = :d, description_talent = :dt "
                    f"WHERE {id_column} = :id"
                )
                payload = [
                    {
                        "id": r["id"],
                        "d": r[description_column],
                        "dt": r.get("description_talent"),
                    }
                    for r in chunk
                ]
            else:
                stmt = text(
                    f"UPDATE {table} SET {description_column} = :d WHERE {id_column} = :id"
                )
                payload = [
                    {"id": r["id"], "d": r[description_column]} for r in chunk
                ]

            def _do(conn: Connection, _stmt=stmt, _payload=payload) -> None:
                conn.execute(_stmt, _payload)
                conn.commit()

            db.run_chunk(_do, max_retries=max_retries, label="description update")
            updated += len(chunk)
            if updated % 5000 == 0 or updated == total:
                print(
                    f"  description refresh progress: {updated}/{total}",
                    flush=True,
                )
    finally:
        db.close()
    return updated


def sync_feed_table(
    dest_conn: Connection,
    source_conn: Connection,
    *,
    table: str,
    select_sql: str,
    columns: list[str],
    id_column: str,
    description_column: str | None = None,
    enriched: dict[int, str] | None = None,
    string_id: bool = False,
    normalize_html: bool = False,
    refresh_descriptions: bool = False,
    two_phase_descriptions: bool = False,
) -> SyncResult:
    """
    Incremental sync: DELETE expired + INSERT new.
    When refresh_descriptions=True (and description_column set), also UPDATE
    description for existing active ids (used after intro/HTML changes).
    Skips ids whose dest description already matches the new payload, so an
    interrupted refresh can resume without re-writing completed rows.

    When two_phase_descriptions=True, the catalog SELECT is slimmed (NULL
    description) and bodies are fetched only for new job_posting_id values.
    """
    enriched = enriched or {}
    has_job_posting_id = "job_posting_id" in columns
    use_two_phase = bool(
        two_phase_descriptions
        and description_column
        and has_job_posting_id
    )

    # text() auto-escapes literal % for pyformat; keep SQL file percents as-is.
    run_sql = slim_feed_select_sql(select_sql) if use_two_phase else select_sql
    if use_two_phase:
        print("  select phase 1: meta only (description deferred)…", flush=True)
    result = source_conn.execute(text(run_sql))
    active_rows = [dict(r._mapping) for r in result.fetchall()]
    print(f"  select returned {len(active_rows)} active rows", flush=True)

    active_ids: set[str | int] = set()
    rows_by_id: dict[str | int, dict[str, Any]] = {}
    for row in active_rows:
        sid = _normalize_id(row[id_column], as_string=string_id)
        active_ids.add(sid)
        rows_by_id[sid] = row

    existing_result = dest_conn.execute(text(f"SELECT {id_column} FROM {table}"))
    existing_ids: set[str | int] = set()
    for r in existing_result.fetchall():
        val = r[0]
        if val is not None:
            existing_ids.add(_normalize_id(val, as_string=string_id))

    expired_ids = sorted(existing_ids - active_ids)
    new_ids = sorted(active_ids - existing_ids)
    keep_ids = sorted(existing_ids & active_ids)
    unchanged = len(keep_ids)

    deleted = _delete_ids(dest_conn, table, id_column, expired_ids)
    if deleted:
        dest_conn.commit()

    need_talent_desc = "description_talent" in columns and bool(description_column)
    talent_normalize = None
    if normalize_html or need_talent_desc:
        from api.platforms.talent import normalize_description_for_talent as talent_normalize

    # One HTML normalize per unique job_posting_id (shared across explode location rows).
    norm_cache: dict[int, str] = {}

    if use_two_phase and new_ids:
        new_jids = sorted(
            {
                int(rows_by_id[nid]["job_posting_id"])
                for nid in new_ids
                if rows_by_id[nid].get("job_posting_id") is not None
            }
        )
        print(
            f"  select phase 2: fetch descriptions for {len(new_jids)} new jobs "
            f"({len(new_ids)} explode rows)…",
            flush=True,
        )
        raw_by_jid = _fetch_job_descriptions(source_conn, new_jids)
        for jid, raw in raw_by_jid.items():
            if normalize_html and talent_normalize is not None:
                norm_cache[jid] = talent_normalize(raw)
            else:
                norm_cache[jid] = raw
        # Attach body onto slim rows so _prepare_row_payload / enriched still work.
        for nid in new_ids:
            row = rows_by_id[nid]
            jid = int(row["job_posting_id"])
            body = norm_cache.get(jid) or raw_by_jid.get(jid)
            if body is not None:
                row[description_column] = body

    # Prepare + insert in waves so dest sockets are not idle for the whole
    # normalize pass (that was causing MySQL 2013 mid-INSERT after ~1h).
    prepare_batch = 500
    inserted = 0
    new_rows: list[dict[str, Any]] = []
    total_new = len(new_ids)
    if total_new:
        print(f"  inserting {total_new} new rows into {table}…", flush=True)
    for i, nid in enumerate(new_ids, start=1):
        payload = _prepare_row_payload(
            rows_by_id[nid],
            columns=columns,
            id_column=id_column,
            description_column=description_column,
            enriched=enriched,
            # Two-phase already normalized into norm_cache; avoid double work.
            normalize_html=normalize_html and not use_two_phase,
            talent_normalize=talent_normalize,
            norm_cache=norm_cache if has_job_posting_id else None,
        )
        if use_two_phase and description_column:
            jid = int(rows_by_id[nid]["job_posting_id"])
            if jid in norm_cache:
                payload[description_column] = norm_cache[jid]
                if "description_talent" in columns:
                    payload["description_talent"] = norm_cache[jid]
        new_rows.append(payload)
        if len(new_rows) >= prepare_batch or i == total_new:
            inserted += _insert_rows(
                dest_conn.engine, table, columns, new_rows
            )
            new_rows = []
            print(
                f"  insert progress: {i}/{total_new} (written≈{inserted})",
                flush=True,
            )

    updated = 0
    # Newly inserted ids are already excluded (keep_ids = existing ∩ active).
    # After a long INSERT wave dest_conn may be idle/stale — use engine so load /
    # update get a fresh socket (same pattern as _insert_rows), with retry.
    if refresh_descriptions and description_column and keep_ids:
        dest_io: Connection | Engine = dest_conn.engine
        if has_job_posting_id:
            # Group explode rows by job; normalize once; UPDATE all rows of that job.
            reps: dict[int, str | int] = {}  # job_posting_id → one feed id
            for nid in keep_ids:
                raw = rows_by_id[nid]
                jid = int(raw["job_posting_id"])
                reps.setdefault(jid, nid)

            if use_two_phase:
                missing = [j for j in reps if j not in norm_cache]
                if missing:
                    print(
                        f"  description refresh: fetch {len(missing)} keep jobs…",
                        flush=True,
                    )
                    raw_keep = _fetch_job_descriptions(source_conn, missing)
                    for jid, raw in raw_keep.items():
                        if normalize_html and talent_normalize is not None:
                            norm_cache[jid] = talent_normalize(raw)
                        else:
                            norm_cache[jid] = raw
                        nid = reps[jid]
                        rows_by_id[nid][description_column] = norm_cache[jid]

            job_payloads: list[dict[str, Any]] = []
            for jid, nid in reps.items():
                payload = _prepare_row_payload(
                    rows_by_id[nid],
                    columns=columns,
                    id_column=id_column,
                    description_column=description_column,
                    enriched=enriched,
                    normalize_html=normalize_html and not use_two_phase,
                    talent_normalize=talent_normalize,
                    norm_cache=norm_cache,
                )
                if use_two_phase and jid in norm_cache:
                    payload[description_column] = norm_cache[jid]
                    if need_talent_desc:
                        payload["description_talent"] = norm_cache[jid]
                job_payloads.append(
                    {
                        "id": nid,
                        "job_posting_id": jid,
                        description_column: payload.get(description_column),
                        "description_talent": payload.get("description_talent"),
                    }
                )

            existing_desc = _load_existing_descriptions(
                dest_io,
                table,
                id_column,
                description_column,
                [j["id"] for j in job_payloads],
                string_id=string_id,
                also_talent=need_talent_desc,
            )
            stale_jobs = _filter_stale_description_rows(
                job_payloads,
                existing_desc,
                description_column,
                also_talent=need_talent_desc,
            )
            skipped = len(job_payloads) - len(stale_jobs)
            if skipped:
                print(
                    f"  description refresh: skip {skipped} jobs already up-to-date, "
                    f"update {len(stale_jobs)} jobs "
                    f"(explode rows≈{len(keep_ids)})",
                    flush=True,
                )
            elif stale_jobs:
                print(
                    f"  description refresh: update {len(stale_jobs)} jobs "
                    f"(explode rows≈{len(keep_ids)})",
                    flush=True,
                )
            updated = _update_descriptions_by_job_posting_id(
                dest_io,
                table,
                description_column,
                stale_jobs,
                also_talent=need_talent_desc,
            )
        else:
            refresh_rows: list[dict[str, Any]] = []
            for nid in keep_ids:
                payload = _prepare_row_payload(
                    rows_by_id[nid],
                    columns=columns,
                    id_column=id_column,
                    description_column=description_column,
                    enriched=enriched,
                    normalize_html=normalize_html,
                    talent_normalize=talent_normalize,
                )
                refresh_rows.append(
                    {
                        "id": nid,
                        description_column: payload.get(description_column),
                        "description_talent": payload.get("description_talent"),
                    }
                )
            existing_desc = _load_existing_descriptions(
                dest_io,
                table,
                id_column,
                description_column,
                [r["id"] for r in refresh_rows],
                string_id=string_id,
                also_talent=need_talent_desc,
            )
            stale_rows = _filter_stale_description_rows(
                refresh_rows,
                existing_desc,
                description_column,
                also_talent=need_talent_desc,
            )
            skipped = len(refresh_rows) - len(stale_rows)
            if skipped:
                print(
                    f"  description refresh: skip {skipped} already up-to-date, "
                    f"update {len(stale_rows)}",
                    flush=True,
                )
            elif stale_rows:
                print(
                    f"  description refresh: update {len(stale_rows)}",
                    flush=True,
                )
            updated = _update_description_rows(
                dest_io,
                table,
                id_column,
                description_column,
                stale_rows,
                also_talent=need_talent_desc,
            )

    # Fresh socket: dest_conn may have been idle through insert + refresh.
    with dest_conn.engine.connect() as count_conn:
        total_row = count_conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
    total = int(total_row or 0)

    return SyncResult(
        active=len(active_ids),
        inserted=inserted,
        deleted=deleted,
        unchanged=unchanged,
        total=total,
        updated=updated,
    )


def _sanitize_talent_row(item: tuple[Any, Any]) -> dict[str, Any]:
    """Picklable helper for parallel Talent description sanitize."""
    from api.platforms.talent import normalize_description_for_talent

    row_id, description = item
    return {"id": row_id, "d": normalize_description_for_talent(description)}


def backfill_jooble_description_talent(
    dest_conn: Connection,
    *,
    batch_size: int = 1000,
    workers: int = 4,
) -> int:
    """Fill description_talent for existing jooble_job_feed rows (NULL only)."""
    from concurrent.futures import ProcessPoolExecutor

    updated = 0
    while True:
        rows = dest_conn.execute(
            text(
                "SELECT id, description FROM jooble_job_feed "
                "WHERE description_talent IS NULL "
                "LIMIT :lim"
            ),
            {"lim": batch_size},
        ).fetchall()
        if not rows:
            break
        items = [(r[0], r[1]) for r in rows]
        if workers <= 1 or len(items) < 50:
            payload = [_sanitize_talent_row(it) for it in items]
        else:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                payload = list(pool.map(_sanitize_talent_row, items, chunksize=25))
        dest_conn.execute(
            text(
                "UPDATE jooble_job_feed "
                "SET description_talent = :d "
                "WHERE id = :id"
            ),
            payload,
        )
        dest_conn.commit()
        updated += len(payload)
        print(f"  description_talent backfill progress: +{len(payload)} total={updated}", flush=True)
    return updated


def upsert_feed_xml_artifact(
    dest_conn: Connection,
    *,
    feed_name: str,
    xml_text: str,
    job_count: int,
) -> dict[str, Any]:
    """Gzip XML and UPSERT into lw.feed_xml_artifact (or default schema).

    Large campaign feeds (e.g. jooble_usa ~100k jobs) produce 100MB+ gzip blobs;
    raise session max_allowed_packet and use stronger compression before INSERT.
    """
    raw = xml_text.encode("utf-8")
    # Stronger gzip for oversized catalogs (USA/row); level 6 is fine for small feeds.
    compresslevel = 9 if len(raw) >= 50_000_000 else 6
    payload = gzip.compress(raw, compresslevel=compresslevel)
    generated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    print(
        f"  artifact {feed_name}: jobs={job_count} "
        f"raw={len(raw)} gzip={len(payload)} compress={compresslevel}",
        flush=True,
    )
    # Allow up to 512MiB packets for this session (capped by server global).
    try:
        dest_conn.execute(text("SET SESSION max_allowed_packet = 536870912"))
    except Exception as exc:  # noqa: BLE001 — best-effort; INSERT may still work
        print(f"  artifact warn: could not raise max_allowed_packet: {exc}", flush=True)

    stmt = text(
        """
        INSERT INTO feed_xml_artifact
            (feed_name, payload, content_type, job_count, bytes_uncompressed, generated_at)
        VALUES
            (:feed_name, :payload, :content_type, :job_count, :bytes_uncompressed, :generated_at)
        ON DUPLICATE KEY UPDATE
            payload = VALUES(payload),
            content_type = VALUES(content_type),
            job_count = VALUES(job_count),
            bytes_uncompressed = VALUES(bytes_uncompressed),
            generated_at = VALUES(generated_at)
        """
    )
    params = {
        "feed_name": feed_name,
        "payload": payload,
        "content_type": "application/xml",
        "job_count": job_count,
        "bytes_uncompressed": len(raw),
        "generated_at": generated_at,
    }
    try:
        dest_conn.execute(stmt, params)
        dest_conn.commit()
    except (OperationalError, DBAPIError, OSError) as exc:
        if not _is_transient_db_error(exc) and "max_allowed_packet" not in str(exc).lower():
            raise
        print(
            f"  artifact retry {feed_name} after {exc.__class__.__name__}: reconnect…",
            flush=True,
        )
        try:
            dest_conn.rollback()
        except Exception:
            pass
        try:
            dest_conn.invalidate()
        except Exception:
            pass
        # Fresh connection from the same engine for the retry.
        with dest_conn.engine.connect() as retry_conn:
            try:
                retry_conn.execute(text("SET SESSION max_allowed_packet = 536870912"))
            except Exception:
                pass
            retry_conn.execute(stmt, params)
            retry_conn.commit()
    return {
        "feed_name": feed_name,
        "job_count": job_count,
        "bytes_uncompressed": len(raw),
        "bytes_gzip": len(payload),
        "generated_at": generated_at.isoformat(),
    }
