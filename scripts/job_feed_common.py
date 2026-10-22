"""Shared helpers for incremental job feed sync (production → lw)."""

from __future__ import annotations

import gzip
import os
from dataclasses import dataclass
from datetime import datetime, timezone
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
    chunk_size: int = 25,
) -> int:
    """Multi-row INSERT in chunks; commit each chunk to avoid long transactions.

    Ignores duplicate primary keys so a retry / concurrent sync that races on
    the same ids does not abort the whole feed (seen on first Adzuna populate).
    """
    if not rows:
        return 0
    col_sql = ", ".join(columns)
    # MySQL: INSERT IGNORE; SQLite (tests): INSERT OR IGNORE
    insert_kw = "INSERT IGNORE" if conn.dialect.name == "mysql" else "INSERT OR IGNORE"
    inserted = 0
    for chunk in _chunked(rows, chunk_size):
        value_groups: list[str] = []
        payload: dict[str, Any] = {}
        for i, row in enumerate(chunk):
            value_groups.append("(" + ", ".join(f":{c}_{i}" for c in columns) + ")")
            for c in columns:
                payload[f"{c}_{i}"] = row.get(c)
        stmt = text(
            f"{insert_kw} INTO {table} ({col_sql}) VALUES {', '.join(value_groups)}"
        )
        result = conn.execute(stmt, payload)
        conn.commit()
        # rowcount is rows actually written (excludes ignored duplicates).
        inserted += max(int(result.rowcount or 0), 0)
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
) -> dict[str, Any]:
    """Build insert/update payload; optionally HTML-normalize description (+ talent)."""
    row = dict(row)
    if description_column and enriched:
        job_id = _job_id_from_row(row, id_column)
        if job_id in enriched:
            row[description_column] = enriched[job_id]
    payload = {c: row.get(c) for c in columns}
    if normalize_html and description_column and talent_normalize is not None:
        norm = talent_normalize(payload.get(description_column))
        payload[description_column] = norm
        if "description_talent" in columns:
            payload["description_talent"] = norm
    elif "description_talent" in columns and description_column and talent_normalize is not None:
        if payload.get("description_talent") is None:
            payload["description_talent"] = talent_normalize(payload.get(description_column))
    return payload


def _update_description_rows(
    conn: Connection,
    table: str,
    id_column: str,
    description_column: str,
    rows: list[dict[str, Any]],
    *,
    also_talent: bool = False,
    chunk_size: int = 100,
) -> int:
    """UPDATE description (+ optional description_talent) for existing feed rows."""
    if not rows:
        return 0
    updated = 0
    for chunk in _chunked(rows, chunk_size):
        if also_talent:
            stmt = text(
                f"UPDATE {table} SET {description_column} = :d, description_talent = :dt "
                f"WHERE {id_column} = :id"
            )
            payload = [
                {"id": r["id"], "d": r[description_column], "dt": r.get("description_talent")}
                for r in chunk
            ]
        else:
            stmt = text(
                f"UPDATE {table} SET {description_column} = :d WHERE {id_column} = :id"
            )
            payload = [{"id": r["id"], "d": r[description_column]} for r in chunk]
        conn.execute(stmt, payload)
        conn.commit()
        updated += len(chunk)
        if updated % 5000 == 0 or updated == len(rows):
            print(f"  description refresh progress: {updated}/{len(rows)}", flush=True)
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
) -> SyncResult:
    """
    Incremental sync: DELETE expired + INSERT new.
    When refresh_descriptions=True (and description_column set), also UPDATE
    description for existing active ids (used after intro/HTML changes).
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
    keep_ids = sorted(existing_ids & active_ids)
    unchanged = len(keep_ids)

    deleted = _delete_ids(dest_conn, table, id_column, expired_ids)
    if deleted:
        dest_conn.commit()

    need_talent_desc = "description_talent" in columns and bool(description_column)
    talent_normalize = None
    if normalize_html or need_talent_desc:
        from api.platforms.talent import normalize_description_for_talent as talent_normalize

    new_rows: list[dict[str, Any]] = []
    for nid in new_ids:
        payload = _prepare_row_payload(
            rows_by_id[nid],
            columns=columns,
            id_column=id_column,
            description_column=description_column,
            enriched=enriched,
            normalize_html=normalize_html,
            talent_normalize=talent_normalize,
        )
        new_rows.append(payload)

    inserted = _insert_rows(dest_conn, table, columns, new_rows)
    # Inserts commit per chunk; this commit is a no-op if nothing pending.
    dest_conn.commit()

    updated = 0
    if refresh_descriptions and description_column and keep_ids:
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
        updated = _update_description_rows(
            dest_conn,
            table,
            id_column,
            description_column,
            refresh_rows,
            also_talent=need_talent_desc,
        )

    total_row = dest_conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
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
    """Gzip XML and UPSERT into lw.feed_xml_artifact (or default schema)."""
    raw = xml_text.encode("utf-8")
    payload = gzip.compress(raw, compresslevel=6)
    generated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    dest_conn.execute(
        text(
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
        ),
        {
            "feed_name": feed_name,
            "payload": payload,
            "content_type": "application/xml",
            "job_count": job_count,
            "bytes_uncompressed": len(raw),
            "generated_at": generated_at,
        },
    )
    dest_conn.commit()
    return {
        "feed_name": feed_name,
        "job_count": job_count,
        "bytes_uncompressed": len(raw),
        "bytes_gzip": len(payload),
        "generated_at": generated_at.isoformat(),
    }
