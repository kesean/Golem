"""
tests/test_embed_docs.py — Unit tests for pure/mockable functions in embed_docs.py.

No real network calls, Voyage API, or Qdrant API are made.
"""

import sys
import os
import hashlib
import uuid

import pytest

# Allow importing from scripts/ which is not a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Stub out env vars required at module import time in embed_docs
os.environ.setdefault("QDRANT_URL", "https://test.qdrant.example.com")
os.environ.setdefault("QDRANT_API_KEY", "test-qdrant-key")
os.environ.setdefault("VOYAGE_API_KEY", "test-voyage-key")

# --- chunk_text tests ---

def test_chunk_text_short_file_produces_one_chunk():
    """A file shorter than CHUNK_TOKENS produces exactly one chunk."""
    from scripts.embed_docs import chunk_text
    text = "hello world"
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0] == text

def test_chunk_text_empty_produces_no_chunks():
    """An empty file produces no chunks."""
    from scripts.embed_docs import chunk_text
    assert chunk_text("") == []

def test_chunk_text_long_file_produces_multiple_chunks():
    """A file longer than CHUNK_TOKENS produces more than one chunk."""
    from scripts.embed_docs import chunk_text, CHUNK_TOKENS
    # Build a text that is definitely longer than one chunk
    word = "documentation "
    text = word * (CHUNK_TOKENS * 2)
    chunks = chunk_text(text)
    assert len(chunks) > 1

def test_chunk_text_overlap_exists():
    """Consecutive chunks share some tokens (overlap)."""
    from scripts.embed_docs import chunk_text, CHUNK_TOKENS
    word = "documentation "
    text = word * (CHUNK_TOKENS * 2)
    chunks = chunk_text(text)
    assert len(chunks) >= 2
    # The start of chunk[1] should overlap with the end of chunk[0]
    assert chunks[1][:10] in chunks[0]

# --- chunk_id tests ---

def test_chunk_id_is_valid_uuid():
    """chunk_id must return a valid UUID string (Qdrant requirement)."""
    from scripts.embed_docs import chunk_id
    result = chunk_id("docs/auth/sessions.mdx", 0)
    parsed = uuid.UUID(result)  # raises ValueError if not valid UUID
    assert str(parsed) == result

def test_chunk_id_is_deterministic():
    """Same inputs always produce the same ID."""
    from scripts.embed_docs import chunk_id
    assert chunk_id("docs/auth/sessions.mdx", 0) == chunk_id("docs/auth/sessions.mdx", 0)

def test_chunk_id_differs_by_path():
    """Different paths produce different IDs."""
    from scripts.embed_docs import chunk_id
    assert chunk_id("docs/auth/sessions.mdx", 0) != chunk_id("docs/auth/tokens.mdx", 0)

def test_chunk_id_differs_by_index():
    """Same path, different index produces different IDs."""
    from scripts.embed_docs import chunk_id
    assert chunk_id("docs/auth/sessions.mdx", 0) != chunk_id("docs/auth/sessions.mdx", 1)
