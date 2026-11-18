"""test_preview_origin.py — PREVIEW_ORIGIN_REGEX is anchored over the whole origin, or disabled if invalid."""

import logging

import pytest

import app as app_module


def test_unset_gives_no_pattern():
    assert app_module._load_preview_origin_pattern("") is None


def test_alternation_cannot_escape_the_anchors():
    """`^a|b$` must not let `https://x` match as a prefix of a longer origin."""
    pattern = app_module._load_preview_origin_pattern(r"^https://a\.com$|https://x")
    assert pattern is not None
    assert pattern.match("https://a.com")
    assert not pattern.match("https://a.com.evil.io")
    assert pattern.match("https://x")
    assert not pattern.match("https://x.evil")


def test_unanchored_value_still_works_and_is_matched_whole():
    pattern = app_module._load_preview_origin_pattern(r"https://golem-.*\.vercel\.app")
    assert pattern is not None
    assert pattern.match("https://golem-abc.vercel.app")
    assert not pattern.match("https://golem-abc.vercel.app.evil.io")


def test_unanchored_value_logs_a_normalisation_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="app"):
        app_module._load_preview_origin_pattern(r"https://golem-.*\.vercel\.app")
    assert any(r.levelno == logging.WARNING and "normalised" in r.message for r in caplog.records)


def test_anchored_value_logs_no_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="app"):
        app_module._load_preview_origin_pattern(r"^https://golem-[a-z0-9-]+\.vercel\.app$")
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]


def test_invalid_regex_disables_preview_and_logs_error(caplog):
    with caplog.at_level(logging.ERROR, logger="app"):
        assert app_module._load_preview_origin_pattern("^https://(unclosed$") is None
    assert any("not a valid regex" in r.message for r in caplog.records)


def test_anchored_pattern_matches_only_previews():
    pattern = app_module._load_preview_origin_pattern(r"^https://golem-[a-z0-9-]+\.vercel\.app$")
    assert pattern.match("https://golem-abc123.vercel.app")
    assert not pattern.match("https://evil.example/?golem-abc.vercel.app")
    assert not pattern.match("https://golem-abc.vercel.app.evil.example")


def test_invalid_preview_leaves_frontend_origin_only():
    origins = app_module._cors_origins_from_env(
        "https://golem.example", app_module._load_preview_origin_pattern("https://golem-(")
    )
    assert origins == ["https://golem.example"]


@pytest.mark.parametrize("raw", [r"^https://golem-.*\.vercel\.app$", r"https://golem-.*\.vercel\.app"])
def test_valid_preview_is_added_after_frontend_origin(raw):
    origins = app_module._cors_origins_from_env(
        "https://golem.example", app_module._load_preview_origin_pattern(raw)
    )
    assert origins[0] == "https://golem.example"
    assert len(origins) == 2
    assert origins[1].match("https://golem-x.vercel.app")
