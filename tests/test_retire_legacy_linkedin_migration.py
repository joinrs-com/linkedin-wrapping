"""Verify retirement is restricted to lw, preserving active feed and source data."""
import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_drop_legacy_tables_preserves_active_tables_and_production_source():
    path = Path(__file__).parents[1] / "api/wrapping/alembic/versions/0026_drop_legacy_linkedin.py"
    spec = importlib.util.spec_from_file_location("retire_legacy_linkedin", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    active = ("jooble_job_feed", "adzuna_job_feed", "whatjobs_job_feed",
              "hirematic_job_feed", "jobrapido_job_feed", "feed_xml_artifact", "job_feed_pipeline_run")
    legacy = ("job_postings", "job_posting_pre", "job_description_enriched")
    with engine.connect() as connection:
        connection.execute(text("ATTACH DATABASE ':memory:' AS lw"))
        connection.execute(text("ATTACH DATABASE ':memory:' AS job_postings"))
        connection.execute(text("CREATE TABLE job_postings.job_postings_1 (id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO job_postings.job_postings_1 VALUES (42)"))
        for table in active:
            connection.execute(text(f"CREATE TABLE lw.{table} (id INTEGER PRIMARY KEY)"))
            connection.execute(text(f"INSERT INTO lw.{table} VALUES (1)"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            for table in ("job_postings", "job_posting_pre"):
                connection.execute(text(f"INSERT INTO lw.{table} (id,position) VALUES (1,'old')"))
            connection.execute(text(
                "INSERT INTO lw.job_description_enriched (job_id,description,enriched_at) "
                "VALUES (1,'old','2026-11-04 00:00:00')"
            ))
            migration.upgrade()
            assert not set(legacy) & set(inspect(connection).get_table_names(schema="lw"))
            for table in active:
                assert connection.execute(text(f"SELECT id FROM lw.{table}")).scalar() == 1
            assert connection.execute(text("SELECT id FROM job_postings.job_postings_1")).scalar() == 42
            migration.downgrade()
            for table in legacy:
                assert connection.execute(text(f"SELECT COUNT(*) FROM lw.{table}")).scalar() == 0
    engine.dispose()
