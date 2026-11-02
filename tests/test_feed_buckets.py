"""Unit tests for campaign feed key mapping."""

from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "scripts"))

from feed_buckets import (  # noqa: E402
    FEED_AMERICAS,
    FEED_ASIA,
    FEED_DE,
    FEED_EU,
    FEED_IT,
    FEED_IT5,
    FEED_ES,
    FEED_FR,
    FEED_ROW,
    FEED_UK,
    FEEDS,
    artifact_name,
    country_code_to_iso2,
    feed_for_row,
    usa_shard_for_job,
)


def test_feeds_count():
    # it, it5, es, usa_1..5, uk, fr, de, eu, americas, asia, row
    assert len(FEEDS) == 15


def test_ita_priority_split():
    assert feed_for_row("ITA", priority=1, job_posting_id=1) == FEED_IT
    assert feed_for_row("ITA", priority=4, job_posting_id=1) == FEED_IT
    assert feed_for_row("ITA", priority=5, job_posting_id=1) == FEED_IT5
    assert feed_for_row("ita", priority=None, job_posting_id=1) == FEED_IT5


def test_named_countries():
    assert feed_for_row("ESP", priority=5, job_posting_id=1) == FEED_ES
    assert feed_for_row("GBR", priority=5, job_posting_id=1) == FEED_UK
    assert feed_for_row("FRA", priority=5, job_posting_id=1) == FEED_FR
    assert feed_for_row("DEU", priority=5, job_posting_id=1) == FEED_DE


def test_usa_shards_stable():
    a = usa_shard_for_job(3218063)
    b = usa_shard_for_job(3218063)
    assert a == b
    assert a.startswith("usa_")
    assert a in {f"usa_{i}" for i in range(1, 6)}
    assert feed_for_row("USA", priority=5, job_posting_id=3218063) == a


def test_regions():
    assert feed_for_row("BEL", priority=5, job_posting_id=1) == FEED_EU
    assert feed_for_row("PRT", priority=5, job_posting_id=1) == FEED_EU
    assert feed_for_row("NLD", priority=5, job_posting_id=1) == FEED_EU
    assert feed_for_row("CAN", priority=5, job_posting_id=1) == FEED_AMERICAS
    assert feed_for_row("BRA", priority=5, job_posting_id=1) == FEED_AMERICAS
    assert feed_for_row("MEX", priority=5, job_posting_id=1) == FEED_AMERICAS
    assert feed_for_row("IND", priority=5, job_posting_id=1) == FEED_ASIA
    assert feed_for_row("AUS", priority=5, job_posting_id=1) == FEED_ROW
    assert feed_for_row("ZAF", priority=5, job_posting_id=1) == FEED_ROW


def test_iso2_and_artifact():
    assert country_code_to_iso2("ITA") == "IT"
    assert artifact_name("jooble", "usa_3") == "jooble_usa_3"
    assert artifact_name("adzuna", "it") == "adzuna_it"
