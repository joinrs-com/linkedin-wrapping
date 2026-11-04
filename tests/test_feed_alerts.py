"""Unit tests for Slack feed alerts / HTTP probe helpers."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "scripts"))

from feed_alerts import (  # noqa: E402
    ProbeResult,
    build_probe_specs,
    evaluate_probe,
    format_artifact_integrity_slack_message,
    format_health_slack_message,
    format_pipeline_slack_message,
    notify_artifact_integrity_failures,
    notify_health_failures,
    post_slack,
    probes_ok,
    public_path_for_feed,
)
from feed_buckets import FEEDS  # noqa: E402


def test_public_path_for_feed_usa_and_country():
    assert public_path_for_feed("jooble", "it") == "/wrapping/jooble/it"
    assert public_path_for_feed("talent", "usa_3") == "/wrapping/talent/us/3"
    assert public_path_for_feed("adzuna", "americas") == "/wrapping/adzuna/americas"


def test_build_probe_specs_covers_platforms_and_live():
    specs = build_probe_specs()
    names = {s.name for s in specs}
    # 3 platforms × 15 feeds + 3 live (no root aliases)
    assert len(specs) == 3 * len(FEEDS) + 3
    assert "jooble" not in names
    assert "jooble_it" in names
    assert "jooble_usa_1" in names
    assert "talent_it5" in names
    assert "adzuna_row" in names
    assert "whatjobs" in names
    assert "hirematic" in names
    assert "jobrapido" in names
    usa = next(s for s in specs if s.name == "jooble_usa_2")
    assert usa.path == "/wrapping/jooble/us/2"
    assert usa.require_gzip is True
    assert usa.check_stale is True


def test_evaluate_probe_success_gzip_and_count():
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    ok, err = evaluate_probe(
        http_status=200,
        job_count=1200,
        content_encoding="gzip",
        min_jobs=1,
        require_gzip=True,
        generated_at="2026-11-02T10:00:00+00:00",
        check_stale=True,
        stale_hours=24,
        now=now,
    )
    assert ok is True
    assert err is None


def test_evaluate_probe_empty_jobs():
    ok, err = evaluate_probe(
        http_status=200,
        job_count=0,
        content_encoding="gzip",
        min_jobs=1,
        require_gzip=True,
        check_stale=False,
    )
    assert ok is False
    assert "job_count=0" in (err or "")


def test_evaluate_probe_stale_artifact():
    now = datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc)
    gen = (now - timedelta(hours=30)).isoformat()
    ok, err = evaluate_probe(
        http_status=200,
        job_count=100,
        content_encoding="gzip",
        min_jobs=1,
        require_gzip=True,
        generated_at=gen,
        check_stale=True,
        stale_hours=24,
        now=now,
    )
    assert ok is False
    assert "stale" in (err or "")


def test_evaluate_probe_live_min_bytes():
    ok, err = evaluate_probe(
        http_status=200,
        job_count=None,
        content_encoding="",
        min_jobs=0,
        require_gzip=False,
        content_length=50,
        min_bytes=200,
    )
    assert ok is False
    assert "content_length" in (err or "")


def test_evaluate_probe_http_error():
    ok, err = evaluate_probe(
        http_status=502,
        job_count=None,
        content_encoding="",
        min_jobs=0,
        require_gzip=False,
    )
    assert ok is False
    assert "502" in (err or "")


def test_format_pipeline_slack_message_includes_all_platforms():
    report = {
        "status": "success",
        "started_at": "2026-11-02T06:00:00",
        "finished_at": "2026-11-02T08:00:00",
        "duration_sec": 7200,
        "feeds": {
            "jooble": {
                "active": 10,
                "inserted": 1,
                "deleted": 0,
                "unchanged": 9,
                "updated": 2,
                "total": 10,
            },
            "whatjobs": {
                "active": 5,
                "inserted": 0,
                "deleted": 0,
                "unchanged": 5,
                "updated": 0,
                "total": 5,
            },
            "hirematic": {
                "active": 3,
                "inserted": 0,
                "deleted": 0,
                "unchanged": 3,
                "updated": 0,
                "total": 3,
            },
            "jobrapido": {
                "active": 4,
                "inserted": 0,
                "deleted": 0,
                "unchanged": 4,
                "updated": 0,
                "total": 4,
            },
            "adzuna": {
                "active": 8,
                "inserted": 0,
                "deleted": 0,
                "unchanged": 8,
                "updated": 0,
                "total": 8,
            },
        },
        "artifacts": {
            "jooble_it": {"job_count": 100, "bytes_gzip": 10, "generated_at": "t"},
            "jooble_usa_1": {"job_count": 200, "bytes_gzip": 20, "generated_at": "t"},
            "talent_it": {"job_count": 100, "bytes_gzip": 10, "generated_at": "t"},
            "adzuna_es": {"job_count": 50, "bytes_gzip": 5, "generated_at": "t"},
        },
    }
    text = format_pipeline_slack_message(report)
    assert "success" in text
    assert "`whatjobs`" in text
    assert "`hirematic`" in text
    assert "`jobrapido`" in text
    assert "`jooble`" in text
    assert "it=100" in text
    assert "us1=200" in text or "us_1=200" in text


def test_format_health_slack_message_lists_failures():
    results = [
        ProbeResult("jooble_it", "/wrapping/jooble/it", True, 200, 10, "gzip", 5),
        ProbeResult(
            "adzuna_uk",
            "/wrapping/adzuna/uk",
            False,
            500,
            None,
            "",
            12,
            error="http_status=500",
        ),
    ]
    text = format_health_slack_message(results, base_url="https://lw.joinrs.com")
    assert "`1` failing" in text
    assert "adzuna_uk" in text
    assert "http_status=500" in text


def test_notify_health_failures_quiet_success(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/X")
    good = [ProbeResult("a", "/a", True, 200, 1, "gzip", 10)]
    with patch("feed_alerts.post_slack") as mocked:
        assert notify_health_failures(good, base_url="https://x", quiet_success=True) is False
        mocked.assert_not_called()


def test_post_slack_noop_without_webhook(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    assert post_slack("hello") is False


def test_post_slack_posts_when_url_set(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/X")
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"ok"
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("feed_alerts.urllib.request.urlopen", return_value=mock_resp) as mocked:
        assert post_slack("hello") is True
        mocked.assert_called_once()
        req = mocked.call_args[0][0]
        assert req.full_url.startswith("https://hooks.slack.com/")


def test_probes_ok_mixed():
    good = ProbeResult("a", "/a", True, 200, 1, "gzip", 10)
    bad = ProbeResult("b", "/b", False, 500, None, "", 10, error="http_status=500")
    assert probes_ok([good]) is True
    assert probes_ok([good, bad]) is False


def test_format_artifact_integrity_slack_message():
    text = format_artifact_integrity_slack_message(
        [
            {
                "feed_name": "jooble_fr",
                "error": "length_mismatch",
                "delta": 2,
                "plen": 10,
                "bytes_gzip": 12,
            }
        ]
    )
    assert "jooble_fr" in text
    assert "length_mismatch" in text
    assert "delta=2" in text


def test_notify_artifact_integrity_quiet_success(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/X")
    with patch("feed_alerts.post_slack") as mocked:
        assert notify_artifact_integrity_failures([], quiet_success=True) is False
        mocked.assert_not_called()
