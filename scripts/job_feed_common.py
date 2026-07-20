"""Shared helpers for incremental job feed sync (production → lw)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine


@dataclass
class SyncResult:
    active: int
    inserted: int
    deleted: int
    unchanged: int
    total: int


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


def create_mysql_engine(url: str) -> Engine:
    eng = create_engine(
        url,
        pool_recycle=3600,
        pool_pre_ping=True,
        echo=False,
    )
    if eng.dialect.name != "mysql":
        raise ValueError(f"Atteso MySQL, trovato {eng.dialect.name}")
    return eng


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
    return int(row[id_column])


def _chunked(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


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
    conn: Connection,
    table: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    *,
    chunk_size: int = 100,
) -> int:
    if not rows:
        return 0
    col_sql = ", ".join(columns)
    inserted = 0
    for chunk in _chunked(rows, chunk_size):
        ph = ", ".join(f":{c}" for c in columns)
        stmt = text(f"INSERT INTO {table} ({col_sql}) VALUES ({ph})")
        for row in chunk:
            payload = {c: row.get(c) for c in columns}
            conn.execute(stmt, payload)
            inserted += 1
    return inserted


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
) -> SyncResult:
    """
    Incremental sync: DELETE expired + INSERT new only.
    Unchanged rows are left untouched (no UPDATE).
    """
    enriched = enriched or {}

    # text() auto-escapes literal % for pyformat; keep SQL file percents as-is.
    result = source_conn.execute(text(select_sql))
    active_rows = [dict(r._mapping) for r in result.fetchall()]

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
    unchanged = len(existing_ids & active_ids)

    deleted = _delete_ids(dest_conn, table, id_column, expired_ids)

    new_rows: list[dict[str, Any]] = []
    for nid in new_ids:
        row = dict(rows_by_id[nid])
        if description_column and enriched:
            job_id = _job_id_from_row(row, id_column)
            if job_id in enriched:
                row[description_column] = enriched[job_id]
        new_rows.append({c: row.get(c) for c in columns})

    inserted = _insert_rows(dest_conn, table, columns, new_rows)
    dest_conn.commit()

    total_row = dest_conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
    total = int(total_row or 0)

    return SyncResult(
        active=len(active_ids),
        inserted=inserted,
        deleted=deleted,
        unchanged=unchanged,
        total=total,
    )
