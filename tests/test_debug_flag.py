"""test_debug_flag.py — The Werkzeug debugger is only enabled by FLASK_DEBUG=1."""

import pytest

from app import debug_enabled


def test_debug_enabled_when_flag_is_one(monkeypatch):
    monkeypatch.setenv("FLASK_DEBUG", "1")
    assert debug_enabled() is True


@pytest.mark.parametrize("value", ["0", "true", "yes", ""])
def test_debug_disabled_for_any_other_value(monkeypatch, value):
    monkeypatch.setenv("FLASK_DEBUG", value)
    assert debug_enabled() is False


def test_debug_disabled_when_flag_unset(monkeypatch):
    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    assert debug_enabled() is False
