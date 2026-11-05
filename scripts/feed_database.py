"""Destination database engine for feed sync, refresh and monitoring scripts.

Callers load the project .env before creating the engine. Importing this module
never loads credentials or opens a database connection.
"""

import os

from sqlalchemy.engine.url import make_url
from sqlmodel import create_engine


def mysql_connect_args(url) -> dict:
    """Shared driver options for source and destination MySQL connections."""
    driver = make_url(url).get_driver_name()
    args = {
        "connection_timeout" if driver == "mysqlconnector" else "connect_timeout": 60,
        "read_timeout": 1800,
        "write_timeout": 1800,
    }
    if driver == "pymysql":
        args["binary_prefix"] = True
    return args


def create_database_engine():
    """Crea l'engine del database con configurazione appropriata."""
    url = os.getenv("DATABASE_URL")
    if not url or not str(url).strip():
        raise ValueError(
            "DATABASE_URL mancante o vuota nel .env. "
            "Esempio: DATABASE_URL=mysql+pymysql://USER:PASSWORD@HOST:3306/NOME_DATABASE"
        )
    try:
        parsed_url = make_url(url)
    except Exception:
        raise ValueError(
            "DATABASE_URL nel .env non è una URL SQLAlchemy valida. "
            "Usa mysql+pymysql://USER:PASSWORD@HOST:PORT/DATABASE su una sola riga; "
            "nella password codifica i caratteri speciali con urllib.parse.quote_plus."
        ) from None

    connect_args: dict = {}
    if parsed_url.get_backend_name() == "sqlite":
        connect_args = {"check_same_thread": False}
    elif parsed_url.get_backend_name() == "mysql":
        connect_args = mysql_connect_args(parsed_url)
    engine = create_engine(
        url,
        pool_recycle=1800,
        pool_pre_ping=True,
        echo=False,
        connect_args=connect_args,
    )

    # Gestione schema per MySQL
    if engine.dialect.name == "mysql":
        engine = engine.execution_options(schema_translate_map={
            "lw": None,
        })

    return engine
