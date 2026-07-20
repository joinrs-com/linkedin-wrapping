"""Pytest configuration: ensure models resolve without lw schema on SQLite."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
