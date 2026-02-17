"""Centralized configuration. Only this module reads environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Prefer enrichment/.env (no DATABASE_URL); fallback to project root .env
_env_dir = Path(__file__).resolve().parent
_env_path = _env_dir / ".env"
_env_path_root = _env_dir.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=True)
elif _env_path_root.exists():
    load_dotenv(_env_path_root, override=True)


def _get_config_env_path() -> Path:
    return _env_path if _env_path.exists() else _env_path_root


def _read_env_var_from_file(var: str) -> str:
    """Read a single var from .env file so enrichment is not affected by os.environ set elsewhere."""
    path = _get_config_env_path()
    if not path.exists():
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() == var:
                        return v.strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


class Settings:
    """Pipeline settings from environment. Database name is never hardcoded."""

    DB_HOST: str = os.getenv("DB_HOST", "")
    DB_PORT: str = os.getenv("DB_PORT", "3306")
    DB_NAME: str = os.getenv("DB_NAME", "")
    DB_USER: str = os.getenv("DB_USER", "")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Limit on LLM calls per run; 0 = unlimited (LLM whenever needed).
    MAX_LLM_CALLS_PER_RUN: int = int(os.getenv("MAX_LLM_CALLS_PER_RUN", "0"))

    # Default processing version written to job_enrichment (plan rule 3)
    DEFAULT_PROCESSING_VERSION: str = os.getenv("PROCESSING_VERSION", "pipeline_v1")

    # LLM model
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    @property
    def database_url(self) -> str:
        """Build connection URL. Prefer values read directly from .env file (DB_NAME=data not overwritten by lw)."""
        host = _read_env_var_from_file("DB_HOST") or os.getenv("DB_HOST", self.DB_HOST)
        port = _read_env_var_from_file("DB_PORT") or os.getenv("DB_PORT", self.DB_PORT) or "3306"
        name = _read_env_var_from_file("DB_NAME") or os.getenv("DB_NAME", self.DB_NAME)
        user = _read_env_var_from_file("DB_USER") or os.getenv("DB_USER", self.DB_USER)
        password = _read_env_var_from_file("DB_PASSWORD") or os.getenv("DB_PASSWORD", self.DB_PASSWORD)
        if not all([host, name, user]):
            return ""
        return (
            f"mysql+mysqlconnector://{user}:{password}"
            f"@{host}:{port}/{name}"
        )

    def validate(self) -> None:
        """Raise ValueError if required settings are missing."""
        missing = []
        if not self.DB_HOST:
            missing.append("DB_HOST")
        if not self.DB_NAME:
            missing.append("DB_NAME")
        if not self.DB_USER:
            missing.append("DB_USER")
        if not self.DB_PASSWORD:
            missing.append("DB_PASSWORD")
        if not self.OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
        if missing:
            raise ValueError(
                f"Missing required env vars: {', '.join(missing)}. "
                "Copy .env.example to .env and set DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, OPENAI_API_KEY."
            )


# Singleton used by the rest of the enrichment package; no other module uses os.getenv
config: Settings = Settings()
