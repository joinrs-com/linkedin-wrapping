"""Unit tests for campaign feed bucket mapping."""

from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "scripts"))

from feed_buckets import (  # noqa: E402
    BUCKET_EU3,
    BUCKET_ITA_ESP,
    BUCKET_ROW,
    BUCKET_USA,
    artifact_name,
    bucket_for_country,
    country_code_to_iso2,
)


def test_bucket_ita_esp():
    assert bucket_for_country("ITA") == BUCKET_ITA_ESP
    assert bucket_for_country("esp") == BUCKET_ITA_ESP


def test_bucket_usa_eu3_row():
    assert bucket_for_country("USA") == BUCKET_USA
    assert bucket_for_country("FRA") == BUCKET_EU3
    assert bucket_for_country("GBR") == BUCKET_EU3
    assert bucket_for_country("DEU") == BUCKET_EU3
    assert bucket_for_country("NLD") == BUCKET_ROW
    assert bucket_for_country("POL") == BUCKET_ROW


def test_iso2_mapping():
    assert country_code_to_iso2("ITA") == "IT"
    assert country_code_to_iso2("USA") == "US"
    assert country_code_to_iso2("GBR") == "GB"
    assert country_code_to_iso2("it") == "IT"


def test_artifact_name():
    assert artifact_name("jooble", "usa") == "jooble_usa"
    assert artifact_name("adzuna", "ita_esp") == "adzuna_ita_esp"
