"""Real-driver regression for MySQL bug #118025; isolated temporary table only.

Set MYSQL_ARTIFACT_TEST_URL to a mysql+mysqlconnector URL. CI provides a disposable
MySQL service. The test never writes to the real feed_xml_artifact table.
"""
import gzip
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import event, text

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))


@pytest.mark.skipif(not os.getenv("MYSQL_ARTIFACT_TEST_URL"), reason="MySQL integration URL not set")
def test_connector_preserves_double_percent_sequences_in_gzip(monkeypatch):
    from feed_database import create_database_engine, database_driver_label
    import job_feed_common as common

    monkeypatch.setenv("DATABASE_URL", os.environ["MYSQL_ARTIFACT_TEST_URL"])
    engine = create_database_engine()
    assert engine.dialect.driver == "mysqlconnector"
    assert database_driver_label(engine) == "mysqlconnector 9.4.0"
    # Uncompressed deflate blocks retain the two %%s sequences in a valid gzip.
    raw = b"%%s" + bytes(range(256)) * 4096 + b"%%s"
    payload = gzip.compress(raw, compresslevel=0, mtime=0)
    assert payload.count(b"%%s") == 2

    def redirect(conn, cursor, statement, parameters, context, executemany):
        # Also protects the retry connection: it cannot hit the production table.
        return statement.replace("feed_xml_artifact", "artifact_percent_probe"), parameters

    try:
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE TEMPORARY TABLE artifact_percent_probe ("
                "feed_name VARCHAR(64) PRIMARY KEY, payload LONGBLOB NULL, "
                "storage_uri VARCHAR(512) NULL, content_type VARCHAR(64) NOT NULL, "
                "job_count INT NOT NULL, bytes_uncompressed BIGINT NOT NULL, "
                "bytes_gzip BIGINT NOT NULL, generated_at DATETIME NOT NULL) ENGINE=InnoDB"
            ))
            conn.commit()
            event.listen(engine, "before_cursor_execute", redirect, retval=True)
            try:
                common._write_mysql_artifact_payload(
                    conn, feed_name="percent_regression", payload=payload,
                    storage_uri=None, job_count=1, bytes_uncompressed=len(raw),
                    generated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
                row = conn.execute(text(
                    "SELECT payload, LENGTH(payload) AS size, SHA2(payload,256) AS digest "
                    "FROM artifact_percent_probe WHERE feed_name='percent_regression'"
                )).mappings().one()
                saved = bytes(row["payload"])
                assert row["size"] == len(payload)
                assert row["digest"] == hashlib.sha256(payload).hexdigest()
                assert saved == payload and saved.count(b"%%s") == 2
                assert gzip.decompress(saved) == raw
            finally:
                event.remove(engine, "before_cursor_execute", redirect)
                conn.rollback()
                conn.execute(text("DROP TEMPORARY TABLE IF EXISTS artifact_percent_probe"))
                conn.commit()
    finally:
        engine.dispose()
