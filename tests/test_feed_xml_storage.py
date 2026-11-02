"""Unit tests for campaign feed XML external storage (file:// / s3://)."""

from __future__ import annotations

import gzip

from utils.feed_xml_storage import get_gzip, iter_gzip, put_gzip, storage_uri_for


def test_put_get_roundtrip_local(tmp_path, monkeypatch):
    monkeypatch.setenv("FEED_XML_STORAGE_DIR", str(tmp_path))
    monkeypatch.delenv("FEED_XML_S3_BUCKET", raising=False)
    payload = gzip.compress(b"<source><job/></source>")
    uri = put_gzip("jooble_ita_esp", payload)
    assert uri.startswith("file://")
    assert get_gzip(uri) == payload
    chunks = b"".join(iter_gzip(uri, chunk_size=8))
    assert chunks == payload
    assert storage_uri_for("jooble_ita_esp") == uri
