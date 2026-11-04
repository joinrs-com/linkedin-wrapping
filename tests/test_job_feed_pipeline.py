"""Tests for incremental job feed sync helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "scripts"))

from job_feed_common import (  # noqa: E402
    _insert_rows,
    load_sql,
    slim_feed_select_sql,
    sync_feed_table,
)


@pytest.mark.parametrize("driver", ["pymysql", "mysqlconnector"])
def test_mysql_engine_options_are_accepted_by_selected_driver(monkeypatch, driver):
    """Validate options with the real DB driver, without opening network sockets."""
    import job_feed_common as common

    real_create_engine = common.create_engine

    def validate_options(url, **kwargs):
        engine = real_create_engine(url, **kwargs)
        args, params = engine.dialect.create_connect_args(engine.url)
        assert not args
        params.update(kwargs["connect_args"])
        if driver == "mysqlconnector":
            from mysql.connector.connection import MySQLConnection
            MySQLConnection().config(**params)
        else:
            from pymysql.connections import Connection
            Connection(defer_connect=True, **params)
        return engine

    monkeypatch.setattr(common, "create_engine", validate_options)
    engine = common.create_mysql_engine(f"mysql+{driver}://test:test@localhost/test")
    engine.dispose()


def test_load_sql_preserves_mysql_percent_literals(tmp_path):
    """DATE_FORMAT / LIKE % stay single; text() escapes on compile."""
    sql_dir = tmp_path / "scripts" / "sql"
    sql_dir.mkdir(parents=True)
    (sql_dir / "sample.sql").write_text(
        "SELECT DATE_FORMAT(x, '%d.%m.%Y') AS d, col LIKE '%Remote%' AS r",
        encoding="utf-8",
    )
    out = load_sql(tmp_path, "sample.sql")
    assert "DATE_FORMAT(x, '%d.%m.%Y')" in out
    assert "LIKE '%Remote%'" in out
    assert "%%" not in out

    compiled = str(text(out).compile(dialect=create_engine("mysql+pymysql://").dialect))
    assert "%%d.%%m.%%Y" in compiled
    assert "%%Remote%%" in compiled


def test_slim_feed_select_sql_strips_jooble_description():
    sql = load_sql(project_root, "jooble_job_feed_select.sql")
    slim = slim_feed_select_sql(sql)
    assert "CAST(NULL AS CHAR) AS description" in slim
    assert "CONCAT('<p>', n.description, '</p>') AS description" not in slim


def test_two_phase_sync_fetches_description_for_new_jobs():
    """Slim SELECT + mocked body fetch fills description on insert."""
    src = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    dest = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with dest.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE feed (
                    id TEXT PRIMARY KEY,
                    job_posting_id INTEGER,
                    description TEXT,
                    title TEXT
                )
                """
            )
        )

    # Expression must match slim_feed_select_sql regex (n.description).
    select_sql = """
        SELECT '99-1' AS id, 99 AS job_posting_id,
               CONCAT('<p>', n.description, '</p>') AS description,
               't' AS title
        FROM (SELECT 'ignored' AS description) AS n
    """

    with patch(
        "job_feed_common._fetch_job_descriptions",
        return_value={99: "<p>from-source</p>"},
    ):
        with src.connect() as src_conn, dest.connect() as dest_conn:
            result = sync_feed_table(
                dest_conn,
                src_conn,
                table="feed",
                select_sql=select_sql,
                columns=["id", "job_posting_id", "description", "title"],
                id_column="id",
                description_column="description",
                string_id=True,
                two_phase_descriptions=True,
            )

    assert result.inserted == 1
    with dest.connect() as conn:
        row = conn.execute(
            text("SELECT description FROM feed WHERE id = '99-1'")
        ).fetchone()
    assert row[0] == "<p>from-source</p>"


@pytest.fixture()
def sqlite_pair():
    src = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    dest = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with dest.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE feed (
                    id INTEGER PRIMARY KEY,
                    description TEXT,
                    title TEXT
                )
                """
            )
        )
        for i in range(1, 11):
            conn.execute(
                text("INSERT INTO feed (id, description, title) VALUES (:id, :d, :t)"),
                {"id": i, "d": f"old-{i}", "t": f"job-{i}"},
            )
    yield src, dest


def test_sync_feed_table_insert_delete_only(sqlite_pair):
    src, dest = sqlite_pair
    select_sql = """
        SELECT 1 AS id, 'desc-1' AS description, 't1' AS title
        UNION ALL SELECT 5, 'desc-5', 't5'
        UNION ALL SELECT 6, 'desc-6', 't6'
        UNION ALL SELECT 11, 'desc-11', 't11'
        UNION ALL SELECT 12, 'desc-12', 't12'
        UNION ALL SELECT 13, 'desc-13', 't13'
        UNION ALL SELECT 14, 'desc-14', 't14'
        UNION ALL SELECT 15, 'desc-15', 't15'
    """
    enriched = {11: "enriched-11"}

    with src.connect() as src_conn, dest.connect() as dest_conn:
        result = sync_feed_table(
            dest_conn,
            src_conn,
            table="feed",
            select_sql=select_sql,
            columns=["id", "description", "title"],
            id_column="id",
            description_column="description",
            enriched=enriched,
        )

    assert result.active == 8
    assert result.inserted == 5
    assert result.deleted == 7
    assert result.unchanged == 3
    assert result.total == 8

    with dest.connect() as conn:
        rows = conn.execute(text("SELECT id, description FROM feed ORDER BY id")).fetchall()
    by_id = {r[0]: r[1] for r in rows}
    assert list(by_id.keys()) == [1, 5, 6, 11, 12, 13, 14, 15]
    assert by_id[11] == "enriched-11"
    assert by_id[1] == "old-1"
    assert result.updated == 0


def test_sync_refresh_descriptions_normalizes_html(sqlite_pair):
    """Existing rows get description UPDATE when refresh_descriptions + normalize_html."""
    src, dest = sqlite_pair
    select_sql = """
        SELECT 1 AS id, '<p>**Hello** world</p>' AS description, 't1' AS title
        UNION ALL SELECT 2, '<p>plain</p>', 't2'
    """
    with src.connect() as src_conn, dest.connect() as dest_conn:
        result = sync_feed_table(
            dest_conn,
            src_conn,
            table="feed",
            select_sql=select_sql,
            columns=["id", "description", "title"],
            id_column="id",
            description_column="description",
            normalize_html=True,
            refresh_descriptions=True,
        )

    assert result.updated == 2
    assert result.inserted == 0
    assert result.deleted == 8  # old ids 3-10 removed; 1-2 kept
    with dest.connect() as conn:
        rows = {
            r[0]: r[1]
            for r in conn.execute(text("SELECT id, description FROM feed ORDER BY id")).fetchall()
        }
    assert "**" not in rows[1]
    assert "<strong>Hello</strong>" in rows[1]

    # Second pass: already up-to-date rows are skipped (resume / re-run).
    with src.connect() as src_conn, dest.connect() as dest_conn:
        again = sync_feed_table(
            dest_conn,
            src_conn,
            table="feed",
            select_sql=select_sql,
            columns=["id", "description", "title"],
            id_column="id",
            description_column="description",
            normalize_html=True,
            refresh_descriptions=True,
        )
    assert again.updated == 0
    assert again.deleted == 0


def test_sync_refresh_normalizes_once_per_job_posting_id():
    """Explode rows of the same job_posting_id share one HTML normalize + one UPDATE."""
    src = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    dest = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with dest.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE feed (
                    id TEXT PRIMARY KEY,
                    job_posting_id INTEGER,
                    description TEXT,
                    title TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO feed (id, job_posting_id, description, title) VALUES "
                "('10-1', 10, 'old', 'a'), ('10-2', 10, 'old', 'b'), ('11-1', 11, 'old', 'c')"
            )
        )

    select_sql = """
        SELECT '10-1' AS id, 10 AS job_posting_id, '<p>**Same**</p>' AS description, 'a' AS title
        UNION ALL SELECT '10-2', 10, '<p>**Same**</p>', 'b'
        UNION ALL SELECT '11-1', 11, '<p>other</p>', 'c'
    """
    calls: list[str] = []

    import api.platforms.talent as talent_mod

    real = talent_mod.normalize_description_for_talent

    def tracking(desc):
        calls.append(str(desc))
        return real(desc)

    with (
        patch.object(talent_mod, "normalize_description_for_talent", side_effect=tracking),
        src.connect() as src_conn,
        dest.connect() as dest_conn,
    ):
        result = sync_feed_table(
            dest_conn,
            src_conn,
            table="feed",
            select_sql=select_sql,
            columns=["id", "job_posting_id", "description", "title"],
            id_column="id",
            description_column="description",
            string_id=True,
            normalize_html=True,
            refresh_descriptions=True,
        )

    # 2 unique jobs normalized (not 3 explode rows)
    assert len(calls) == 2
    assert result.updated == 2
    with dest.connect() as conn:
        descs = {
            r[0]: r[1]
            for r in conn.execute(text("SELECT id, description FROM feed ORDER BY id")).fetchall()
        }
    assert descs["10-1"] == descs["10-2"]
    assert "**" not in descs["10-1"]
    assert "<strong>Same</strong>" in descs["10-1"]


def test_insert_rows_uses_multi_row_insert_per_chunk(sqlite_pair):
    """One execute per chunk (multi-row VALUES), not one execute per row."""
    _, dest = sqlite_pair
    rows = [
        {"id": 100 + i, "description": f"d-{i}", "title": f"t-{i}"}
        for i in range(7)
    ]
    execute_calls: list[str] = []

    with dest.connect() as conn:
        real_execute = conn.execute

        def tracking_execute(statement, *args, **kwargs):
            sql = str(statement)
            if sql.strip().upper().startswith("INSERT"):
                execute_calls.append(sql)
            return real_execute(statement, *args, **kwargs)

        conn.execute = tracking_execute  # type: ignore[method-assign]
        inserted = _insert_rows(
            conn,
            "feed",
            ["id", "description", "title"],
            rows,
            chunk_size=3,
        )

    assert inserted == 7
    assert len(execute_calls) == 3  # chunks of 3, 3, 1
    assert "INSERT OR IGNORE" in execute_calls[0].upper()
    assert execute_calls[0].count("VALUES") == 1
    assert execute_calls[0].count("(") >= 4  # column list + 3 value groups
    assert ":id_0" in execute_calls[0] and ":id_1" in execute_calls[0]

    with dest.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM feed WHERE id >= 100")).scalar()
    assert count == 7


@pytest.mark.parametrize("integrity_error", [False, True])
def test_artifact_pipeline_reports_without_openai(monkeypatch, integrity_error):
    """Retiring OpenAI must preserve artifact generation and success/failure reports."""
    import run_job_feed_pipeline as pipeline
    from api.wrapping.models import JobFeedPipelineRun
    from feed_database import create_database_engine
    from sqlmodel import SQLModel, select

    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("JOB_FEED_SOURCE_DATABASE_URL", raising=False)
    engine = create_database_engine()
    SQLModel.metadata.create_all(engine, tables=[JobFeedPipelineRun.__table__])
    monkeypatch.setattr(pipeline, "create_database_engine", lambda: engine)
    stats = {"jooble_it": {"job_count": 1, "bytes_uncompressed": 20, "bytes_gzip": 30}}
    monkeypatch.setattr(pipeline, "_generate_feed_xml_artifacts", lambda *a, **kw: stats)

    def verify(*args, **kwargs):
        if integrity_error:
            raise RuntimeError("artifact integrity failure")

    monkeypatch.setattr(pipeline, "_assert_artifact_integrity", verify)
    notifications = []
    monkeypatch.setattr(pipeline, "notify_pipeline_result", notifications.append)
    if integrity_error:
        with pytest.raises(RuntimeError, match="artifact integrity failure"):
            pipeline.run_pipeline(artifacts_only=True)
    else:
        report = pipeline.run_pipeline(artifacts_only=True)
        assert report["artifacts"] == stats

    with Session(engine) as session:
        run = session.exec(select(JobFeedPipelineRun)).one()
        assert run.status == ("failed" if integrity_error else "success")
        assert run.openai_processed == run.enriched_deleted == run.enriched_total == 0
    assert len(notifications) == 1
    assert notifications[0]["status"] == run.status
    engine.dispose()


def test_default_pipeline_syncs_all_feeds_and_records_run(monkeypatch):
    """Exercise the CronJob's default entry point without production writes."""
    import run_job_feed_pipeline as pipeline
    from api.wrapping.models import JobFeedPipelineRun
    from feed_database import create_database_engine
    from sqlmodel import SQLModel, select

    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("JOB_FEED_SOURCE_DATABASE_URL", "mysql+pymysql://unused/source")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    engine = create_database_engine()
    SQLModel.metadata.create_all(engine, tables=[JobFeedPipelineRun.__table__])
    monkeypatch.setattr(pipeline, "create_database_engine", lambda: engine)
    monkeypatch.setattr(pipeline, "create_mysql_engine", lambda url: engine)
    monkeypatch.setattr(pipeline, "purge_archived_job_postings_from_feeds", lambda *a: {})
    synced = []

    def sync(dest, source, **kwargs):
        assert kwargs["select_sql"]
        assert kwargs["enriched"] == {}
        assert kwargs["refresh_descriptions"] is False
        synced.append(kwargs["table"])
        return pipeline.SyncResult(active=2, inserted=1, deleted=0, unchanged=1, total=2)

    monkeypatch.setattr(pipeline, "sync_feed_table", sync)
    monkeypatch.setattr(pipeline, "backfill_jooble_description_talent", lambda *a: 0)
    artifacts = []
    monkeypatch.setattr(
        pipeline, "_generate_feed_xml_artifacts",
        lambda *a, **kw: artifacts.append("generated") or {},
    )
    monkeypatch.setattr(
        pipeline, "_assert_artifact_integrity",
        lambda *a, **kw: artifacts.append("verified"),
    )
    monkeypatch.setattr(pipeline, "notify_pipeline_result", lambda report: None)
    report = pipeline.run_pipeline()

    assert synced == [cfg.table for cfg in pipeline.FEED_CONFIGS]
    assert artifacts == ["generated", "verified"]
    assert report["status"] == "success"
    assert set(report["feeds"]) == {cfg.name for cfg in pipeline.FEED_CONFIGS}
    with Session(engine) as session:
        run = session.exec(select(JobFeedPipelineRun)).one()
        assert run.status == "success"
        assert run.jooble_total == run.adzuna_total == run.whatjobs_total == 2
        assert run.hirematic_total == run.jobrapido_total == 2
        assert run.openai_processed == 0
    engine.dispose()
