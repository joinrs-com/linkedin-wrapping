import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy import create_engine
from sqlmodel import SQLModel
from dotenv import load_dotenv


# Ensure project root is on sys.path so 'api.wrapping' imports work
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Load .env from service root so DATABASE_URL is available
dotenv_path = os.path.join(PROJECT_ROOT, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

# Import only wrapping models so metadata contains just this service
from api.wrapping import models as wrapping_models  # noqa: F401


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata

LW_SCHEMA = "lw"
VERSION_TABLE = "lw_alembic_version"


def get_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is required for Alembic migrations")
    return url


def run_migrations_offline() -> None:
    url = get_url()
    tmp_engine = create_engine(url, poolclass=pool.NullPool)
    is_mysql = tmp_engine.dialect.name == "mysql"

    schema_translate_map = {LW_SCHEMA: None} if is_mysql else None
    version_table_schema = None if is_mysql else LW_SCHEMA

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table=VERSION_TABLE,
        version_table_schema=version_table_schema,
        schema_translate_map=schema_translate_map,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = get_url()
    engine = create_engine(url, poolclass=pool.NullPool, pool_pre_ping=True)

    is_mysql = engine.dialect.name == "mysql"
    schema_translate_map = {LW_SCHEMA: None} if is_mysql else None
    version_table_schema = None if is_mysql else LW_SCHEMA

    with engine.connect() as connection:
        connection = connection.execution_options(schema_translate_map=schema_translate_map or {})

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table=VERSION_TABLE,
            version_table_schema=version_table_schema,
            schema_translate_map=schema_translate_map,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

