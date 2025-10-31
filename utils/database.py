import os
from pathlib import Path

from dotenv import load_dotenv
from sqlmodel import create_engine, Session

# Load .env file before reading DATABASE_URL
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

database_url = os.getenv('DATABASE_URL', 'sqlite:///:memory:')

engine = create_engine(
    database_url,
    pool_recycle=3600,
    pool_pre_ping=True,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in database_url else {})

# Ensure SQLAlchemy ignores explicit schemas on MySQL so service-scoped schemas
# like "lw" map to the current database transparently.
if engine.dialect.name == "mysql":
    engine = engine.execution_options(schema_translate_map={
        "lw": None,
    })


def get_session():
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


def get_session_instance():
    return Session(engine)


