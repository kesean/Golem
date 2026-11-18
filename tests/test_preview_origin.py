"""test_preview_origin.py — PREVIEW_ORIGIN_REGEX must be anchored and compile, or it is refused."""

import logging

import pytest

import app as app_module


def test_unset_gives_no_pattern():
    assert app_module._load_preview_origin_pattern("") is None


@pytest.mark.parametrize("raw", [
    "https://golem-.*\\.vercel\\.app",   # unanchored
    "^https://golem-.*\\.vercel\\.app",  # no end anchor
    "https://golem-.*\\.vercel\\.app$",  # no start anchor
])
def test_unanchored_pattern_is_refused_and_logged(raw, caplog):
    with caplog.at_level(logging.ERROR, logger="app"):
        assert app_module._load_preview_origin_pattern(raw) is None
    assert any(r.levelno == logging.ERROR and "PREVIEW_ORIGIN_REGEX" in r.message for r in caplog.records)


def test_invalid_regex_is_refused_and_logged_not_raised(caplog):
    with caplog.at_level(logging.ERROR, logger="app"):
        assert app_module._load_preview_origin_pattern("^https://(unclosed$") is None
    assert any("not a valid regex" in r.message for r in caplog.records)


def test_anchored_pattern_is_compiled_and_matches_only_previews():
    pattern = app_module._load_preview_origin_pattern(r"^https://golem-[a-z0-9-]+\.vercel\.app$")
    assert pattern is not None
    assert pattern.match("https://golem-abc123.vercel.app")
    assert not pattern.match("https://evil.example/?golem-abc.vercel.app")
    assert not pattern.match("https://golem-abc.vercel.app.evil.example")


def test_refused_preview_leaves_frontend_origin_only():
    origins = app_module._cors_origins_from_env("https://golem.example", "https://golem-.*")
    assert origins == ["https://golem.example"]


def test_valid_preview_is_added_after_frontend_origin():
    origins = app_module._cors_origins_from_env("https://golem.example", r"^https://golem-.*\.vercel\.app$")
    assert origins[0] == "https://golem.example"
    assert len(origins) == 2
    assert origins[1].match("https://golem-x.vercel.app")
