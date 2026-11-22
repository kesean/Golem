"""test_limiter_storage.py — Startup check that makes a fail-open limiter loud."""

import logging
from unittest.mock import patch

import app as app_module


def test_reports_unreachable_redis_as_error(caplog):
    with patch.object(app_module, "_redis_url", "redis://x"), \
         patch.object(app_module.limiter.storage, "check", return_value=False), \
         caplog.at_level(logging.INFO, logger="app"):
        assert app_module.check_limiter_storage() is False
    assert any(r.levelno == logging.ERROR and "NOT enforced" in r.message for r in caplog.records)


def test_reports_raising_check_as_error(caplog):
    with patch.object(app_module, "_redis_url", "redis://x"), \
         patch.object(app_module.limiter.storage, "check", side_effect=ConnectionError("boom")), \
         caplog.at_level(logging.INFO, logger="app"):
        assert app_module.check_limiter_storage() is False
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_warns_when_redis_url_unset(caplog):
    with patch.object(app_module, "_redis_url", None), caplog.at_level(logging.INFO, logger="app"):
        assert app_module.check_limiter_storage() is False
    assert any(r.levelno == logging.WARNING and "REDIS_URL" in r.message for r in caplog.records)


def test_healthy_redis_logs_info_only(caplog):
    with patch.object(app_module, "_redis_url", "redis://x"), \
         patch.object(app_module.limiter.storage, "check", return_value=True), \
         caplog.at_level(logging.INFO, logger="app"):
        assert app_module.check_limiter_storage() is True
    assert all(r.levelno == logging.INFO for r in caplog.records)


def test_runtime_storage_failure_warns_once_per_process(rate_limited_client, caplog, monkeypatch):
    """Two requests with storage down: the request still succeeds, and exactly one WARNING is logged."""
    monkeypatch.setattr(app_module._limiter_failure_watch, "tripped", False)
    with patch.object(app_module.limiter.limiter, "test", side_effect=ConnectionError("redis down")), \
         patch.object(app_module.limiter.limiter, "hit", side_effect=ConnectionError("redis down")), \
         caplog.at_level(logging.WARNING, logger="app"):
        for _ in range(2):
            resp = rate_limited_client.post("/guest-token")
            assert resp.status_code == 200
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and "NOT enforced" in r.message]
    assert len(warnings) == 1
    assert "redis down" in warnings[0].message


def test_runtime_warning_not_repeated_after_first_failure(monkeypatch, caplog):
    monkeypatch.setattr(app_module._limiter_failure_watch, "tripped", True)
    with caplog.at_level(logging.WARNING, logger="app"):
        logging.getLogger("flask-limiter").error("Failed to rate limit. Swallowing error")
    assert not [r for r in caplog.records if "NOT enforced" in r.message]
