"""Unit tests for feed_xml_artifact integrity helpers."""

from __future__ import annotations

import gzip
import sys
from pathlib import Path
from unittest.mock import MagicMock

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "scripts"))

from job_feed_common import (  # noqa: E402
    campaign_artifact_feed_names,
    check_feed_xml_artifact_integrity,
)


def test_campaign_artifact_feed_names_includes_feeds_only():
    names = campaign_artifact_feed_names(("jooble",))
    assert "jooble" not in names
    assert "jooble_it" in names
    assert "jooble_usa_1" in names
    assert "talent_it" not in names


def test_check_feed_xml_artifact_integrity_length_mismatch():
    blob = gzip.compress(b"<source/>")
    conn = MagicMock()
    result = MagicMock()
    result.mappings.return_value.all.return_value = [
        {
            "feed_name": "jooble_fr",
            "job_count": 1,
            "plen": len(blob) - 2,
            "bytes_gzip": len(blob),
            "storage_uri": None,
            "payload": blob[:-2],
        }
    ]
    conn.execute.return_value = result
    failures = check_feed_xml_artifact_integrity(
        conn, feed_names=["jooble_fr"], gunzip=False
    )
    assert len(failures) == 1
    assert failures[0]["error"] == "length_mismatch"
    assert failures[0]["delta"] == 2


def test_check_feed_xml_artifact_integrity_ok():
    blob = gzip.compress(b"<source><job/></source>")
    conn = MagicMock()
    result = MagicMock()
    result.mappings.return_value.all.return_value = [
        {
            "feed_name": "jooble_it",
            "job_count": 1,
            "plen": len(blob),
            "bytes_gzip": len(blob),
            "storage_uri": None,
            "payload": blob,
        }
    ]
    conn.execute.return_value = result
    failures = check_feed_xml_artifact_integrity(
        conn, feed_names=["jooble_it"], gunzip=True
    )
    assert failures == []
