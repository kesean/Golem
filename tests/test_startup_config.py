"""test_startup_config.py — Startup refuses unsafe config in production and weak guest secrets anywhere."""

import os
import subprocess
import sys

import pytest

from app import check_startup_config

STRONG_SECRET = "x" * 32
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_importing_app_in_production_without_redis_url_exits_nonzero():
    """The module-level call must run on import, not only the function when called directly."""
    env = {k: v for k, v in os.environ.items() if k not in ("REDIS_URL", "GUEST_JWT_SECRET")}
    env.update({"VERCEL": "1", "VERCEL_ENV": "production", "GUEST_JWT_SECRET": STRONG_SECRET, "ANTHROPIC_API_KEY": "test-key-placeholder"})
    proc = subprocess.run(
        [sys.executable, "-c", "import app"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode != 0
    assert "REDIS_URL is required on Vercel" in proc.stderr


def test_production_without_redis_url_refuses_to_start():
    with pytest.raises(RuntimeError, match="REDIS_URL is required on Vercel"):
        check_startup_config({"VERCEL": "1", "VERCEL_ENV": "production", "GUEST_JWT_SECRET": STRONG_SECRET})


def test_production_with_redis_url_starts():
    check_startup_config({"VERCEL": "1", "VERCEL_ENV": "production", "REDIS_URL": "redis://x", "GUEST_JWT_SECRET": STRONG_SECRET})


def test_preview_without_redis_or_guest_secret_starts():
    check_startup_config({"VERCEL": "1", "VERCEL_ENV": "preview"})


def test_local_without_redis_url_still_starts():
    check_startup_config({"GUEST_JWT_SECRET": STRONG_SECRET})


def test_short_guest_secret_refuses_to_start():
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        check_startup_config({"REDIS_URL": "redis://x", "GUEST_JWT_SECRET": "x" * 31})


def test_short_guest_secret_refuses_to_start_on_preview():
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        check_startup_config({"VERCEL": "1", "VERCEL_ENV": "preview", "GUEST_JWT_SECRET": "x" * 31})


def test_guest_secret_of_exactly_32_characters_is_accepted():
    check_startup_config({"GUEST_JWT_SECRET": "x" * 32})


def test_unset_guest_secret_is_allowed_off_vercel():
    check_startup_config({})


def test_unset_guest_secret_refuses_to_start_in_production():
    with pytest.raises(RuntimeError, match="GUEST_JWT_SECRET is required on Vercel"):
        check_startup_config({"VERCEL": "1", "VERCEL_ENV": "production", "REDIS_URL": "redis://x"})
