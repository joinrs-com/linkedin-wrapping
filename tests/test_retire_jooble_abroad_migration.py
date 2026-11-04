"""Exercise the table retirement migration against a real isolated SQL database."""

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_retire_abroad_upgrade_and_schema_downgrade():
    path = Path(__file__).parents[1] / "api/wrapping/alembic/versions/0025_drop_jooble_abroad.py"
    spec = importlib.util.spec_from_file_location("retire_abroad", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.execute(text("ATTACH DATABASE ':memory:' AS lw"))
        connection.execute(text("CREATE TABLE lw.jooble_job_feed (id TEXT PRIMARY KEY)"))
        connection.execute(text("INSERT INTO lw.jooble_job_feed VALUES ('active')"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            connection.execute(text(
                "INSERT INTO lw.jooble_abroad_job_feed (id, job_posting_id, position) "
                "VALUES ('1-1', 1, 'Old role')"
            ))
            migration.upgrade()
            assert not inspect(connection).has_table("jooble_abroad_job_feed", schema="lw")
            assert connection.execute(text("SELECT id FROM lw.jooble_job_feed")).scalar() == "active"
            migration.downgrade()
            assert connection.execute(text("SELECT COUNT(*) FROM lw.jooble_abroad_job_feed")).scalar() == 0
            indexes = inspect(connection).get_indexes("jooble_abroad_job_feed", schema="lw")
            assert any(index["column_names"] == ["job_posting_id"] for index in indexes)
    engine.dispose()
