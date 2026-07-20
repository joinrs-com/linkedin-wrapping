"""Tests for incremental job feed sync and enrichment helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "scripts"))

from job_feed_common import (  # noqa: E402
    load_sql,
    sync_feed_table,
)


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


def test_should_enrich_requires_italy_and_priority():
    import improve_job_descriptions as ijd

    assert ijd.should_enrich_with_openai(priority=2, has_ita=1, employers_id=123) is True
    assert ijd.should_enrich_with_openai(priority=2, has_ita=0, employers_id=123) is False
    assert ijd.should_enrich_with_openai(priority=4, has_ita=1, employers_id=123) is False
    assert ijd.should_enrich_with_openai(priority=1, has_ita=1, employers_id=829928) is False


def test_run_enrichment_skips_existing(monkeypatch):
    import improve_job_descriptions as ijd
    from sqlmodel import SQLModel

    from api.wrapping.models import JobDescriptionEnriched

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine, tables=[JobDescriptionEnriched.__table__])

    inputs = [
        {"job_id": 1, "input_description": "<p>a</p>", "priority": 2, "has_ita": 1, "employers_id": 100},
        {"job_id": 2, "input_description": "<p>b</p>", "priority": 2, "has_ita": 1, "employers_id": 101},
    ]
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        ijd,
        "improve_job_description_with_openai",
        lambda job_description, strict=False: f"AI:{job_description}",
    )

    first = ijd.run_enrichment_pipeline(inputs, engine=engine)
    assert first.processed == 2
    assert first.total == 2

    second = ijd.run_enrichment_pipeline(inputs, engine=engine)
    assert second.processed == 0
    assert second.total == 2


def test_enrichment_aborts_on_openai_error(monkeypatch):
    import improve_job_descriptions as ijd
    from sqlmodel import SQLModel, select

    from api.wrapping.models import JobDescriptionEnriched

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine, tables=[JobDescriptionEnriched.__table__])

    inputs = [
        {"job_id": 1, "input_description": "<p>a</p>", "priority": 2, "has_ita": 1, "employers_id": 100},
        {"job_id": 2, "input_description": "<p>b</p>", "priority": 2, "has_ita": 1, "employers_id": 101},
    ]

    def _raise_on_strict(job_description, strict=False):
        if strict:
            raise ijd.OpenAIEnrichmentError("invalid_api_key")
        return job_description

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(ijd, "improve_job_description_with_openai", _raise_on_strict)

    with pytest.raises(ijd.OpenAIEnrichmentError):
        ijd.run_enrichment_pipeline(inputs, engine=engine)

    with Session(engine) as session:
        rows = session.exec(select(JobDescriptionEnriched)).all()
    assert len(rows) == 0


def test_improve_job_description_strict_raises(monkeypatch):
    import improve_job_descriptions as ijd
    import openai

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            raise Exception("401 invalid_api_key")

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(openai, "OpenAI", lambda api_key: FakeClient())

    with pytest.raises(ijd.OpenAIEnrichmentError):
        ijd.improve_job_description_with_openai("<p>x</p>", strict=True)

    assert ijd.improve_job_description_with_openai("<p>x</p>", strict=False) == "<p>x</p>"
