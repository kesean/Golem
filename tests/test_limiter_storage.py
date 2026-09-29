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
