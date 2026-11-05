"""Unit tests for feed_xml_artifact integrity helpers."""

from __future__ import annotations

import gzip
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import LargeBinary, bindparam, create_engine, text

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


@pytest.mark.parametrize("corrupt_write", [False, True])
def test_artifact_publishes_only_after_integrity_validation(tmp_path, monkeypatch, corrupt_write):
    """A corrupt replacement must roll back both attempts and retain the old gzip."""
    import job_feed_common as common

    engine = create_engine(f"sqlite:///{tmp_path / 'artifacts.db'}")
    old_payload = gzip.compress(b"<source>previous valid feed</source>", mtime=0)
    new_payload = gzip.compress(bytes(range(256)) * 1024, mtime=0)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE feed_xml_artifact "
            "(feed_name TEXT PRIMARY KEY, payload BLOB, bytes_gzip INTEGER)"
        ))
        conn.execute(text("INSERT INTO feed_xml_artifact VALUES ('probe', :p, :n)"),
                     {"p": old_payload, "n": len(old_payload)})
        if corrupt_write:
            conn.execute(text(
                "CREATE TRIGGER corrupt_artifact AFTER UPDATE ON feed_xml_artifact BEGIN "
                "UPDATE feed_xml_artifact SET payload=substr(NEW.payload,1,length(NEW.payload)-2) "
                "WHERE feed_name=NEW.feed_name; END"
            ))

    stmt = text(
        "UPDATE feed_xml_artifact SET payload=:payload, bytes_gzip=:bytes_gzip "
        "WHERE feed_name=:feed_name"
    ).bindparams(bindparam("payload", type_=LargeBinary()))
    monkeypatch.setattr(common, "_artifact_upsert_stmt", lambda: stmt)
    monkeypatch.setattr(common, "_raise_max_allowed_packet", lambda conn: None)
    real_verify = common._verify_mysql_artifact_payload

    def verify(conn, **kwargs):
        # Readers must still see the previous artifact until validation finishes.
        with engine.connect() as reader:
            assert reader.execute(text("SELECT payload FROM feed_xml_artifact")).scalar() == old_payload
        real_verify(conn, **kwargs)

    monkeypatch.setattr(common, "_verify_mysql_artifact_payload", verify)
    with engine.connect() as conn:
        kwargs = dict(feed_name="probe", payload=new_payload, storage_uri=None,
                      job_count=1, bytes_uncompressed=262144,
                      generated_at=datetime.now(timezone.utc).replace(tzinfo=None))
        if corrupt_write:
            with pytest.raises(RuntimeError, match="failed after retry"):
                common._write_mysql_artifact_payload(conn, **kwargs)
        else:
            common._write_mysql_artifact_payload(conn, **kwargs)
    with engine.connect() as conn:
        saved = conn.execute(text("SELECT payload FROM feed_xml_artifact")).scalar()
        assert saved == (old_payload if corrupt_write else new_payload)
        gzip.decompress(saved)
    engine.dispose()
