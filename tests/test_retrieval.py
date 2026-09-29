"""test_retrieval.py — Unit tests for retrieval.py."""
from unittest.mock import MagicMock
import retrieval


def _make_hit(source, path, text):
    hit = MagicMock()
    hit.payload = {"source": source, "repo_path": path, "text": text}
    return hit


def test_retrieve_chunks_returns_structured_hits(monkeypatch):
    """retrieve_chunks returns dicts with source/path/text/url, most relevant first."""
    mock_voyage = MagicMock()
    mock_voyage.embed.return_value.embeddings = [[0.1] * 512]
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = [
        _make_hit("Clerk", "docs/authentication/sessions.mdx", "Session info here."),
        _make_hit("MDN", "files/en-us/web/api/fetch_api/index.md", "Fetch API docs."),
    ]
    monkeypatch.setattr(retrieval, "_voyage", mock_voyage)
    monkeypatch.setattr(retrieval, "_qdrant", mock_qdrant)

    chunks = retrieval.retrieve_chunks("How do I verify a session?")

    assert chunks == [
        {"source": "Clerk", "path": "docs/authentication/sessions.mdx", "text": "Session info here.", "url": "https://clerk.com/docs/authentication/sessions"},
        {"source": "MDN", "path": "files/en-us/web/api/fetch_api/index.md", "text": "Fetch API docs.", "url": "https://developer.mozilla.org/en-US/docs/web/api/fetch_api"},
    ]


def test_retrieve_chunks_empty_list_when_no_results(monkeypatch):
    """Qdrant returns no hits — retrieve_chunks returns []."""
    mock_voyage = MagicMock()
    mock_voyage.embed.return_value.embeddings = [[0.1] * 512]
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = []
    monkeypatch.setattr(retrieval, "_voyage", mock_voyage)
    monkeypatch.setattr(retrieval, "_qdrant", mock_qdrant)

    assert retrieval.retrieve_chunks("some question") == []


def test_retrieve_chunks_empty_list_when_qdrant_client_is_none(monkeypatch):
    """_qdrant is None (QDRANT_URL missing at startup) — returns [] without raising."""
    monkeypatch.setattr(retrieval, "_qdrant", None)
    monkeypatch.setattr(retrieval, "_voyage", MagicMock())

    assert retrieval.retrieve_chunks("some question") == []


def test_retrieve_chunks_empty_list_when_voyage_client_is_none(monkeypatch):
    """_voyage is None (VOYAGE_API_KEY missing at startup) — returns [] without raising."""
    monkeypatch.setattr(retrieval, "_qdrant", MagicMock())
    monkeypatch.setattr(retrieval, "_voyage", None)

    assert retrieval.retrieve_chunks("some question") == []


def test_retrieve_chunks_empty_list_when_voyage_raises(monkeypatch):
    """Voyage API call fails — returns [], does not raise."""
    mock_voyage = MagicMock()
    mock_voyage.embed.side_effect = Exception("Voyage API error")
    monkeypatch.setattr(retrieval, "_voyage", mock_voyage)
    monkeypatch.setattr(retrieval, "_qdrant", MagicMock())

    assert retrieval.retrieve_chunks("some question") == []


def test_retrieve_chunks_empty_list_on_failure(monkeypatch):
    """retrieve_chunks returns [] rather than raising when Qdrant fails."""
    mock_voyage = MagicMock()
    mock_voyage.embed.return_value.embeddings = [[0.1] * 512]
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.side_effect = Exception("Qdrant connection error")
    monkeypatch.setattr(retrieval, "_voyage", mock_voyage)
    monkeypatch.setattr(retrieval, "_qdrant", mock_qdrant)

    assert retrieval.retrieve_chunks("some question") == []


def test_source_filter_passed_to_qdrant_when_provided(monkeypatch):
    """When source='clerk' is passed, query_points is called with a filter on source == 'clerk'."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    mock_voyage = MagicMock()
    mock_voyage.embed.return_value.embeddings = [[0.1] * 512]
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = []
    monkeypatch.setattr(retrieval, "_voyage", mock_voyage)
    monkeypatch.setattr(retrieval, "_qdrant", mock_qdrant)

    retrieval.retrieve_chunks("How do I verify a session?", source="clerk")

    call_kwargs = mock_qdrant.query_points.call_args.kwargs
    query_filter = call_kwargs.get("query_filter")
    assert query_filter is not None
    expected_filter = Filter(
        must=[FieldCondition(key="source", match=MatchValue(value="clerk"))]
    )
    assert query_filter == expected_filter


def test_no_filter_when_source_is_none(monkeypatch):
    """When source=None (default), query_points is called with query_filter=None."""
    mock_voyage = MagicMock()
    mock_voyage.embed.return_value.embeddings = [[0.1] * 512]
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = []
    monkeypatch.setattr(retrieval, "_voyage", mock_voyage)
    monkeypatch.setattr(retrieval, "_qdrant", mock_qdrant)

    retrieval.retrieve_chunks("some question", source=None)

    call_kwargs = mock_qdrant.query_points.call_args.kwargs
    assert call_kwargs.get("query_filter") is None


def test_retrieve_context_and_chunks_returns_both(monkeypatch):
    """retrieve_context_and_chunks pairs the formatted block with its source chunks."""
    mock_voyage = MagicMock()
    mock_voyage.embed.return_value.embeddings = [[0.1] * 512]
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = [
        _make_hit("Clerk", "docs/authentication/sessions.mdx", "Session info here."),
        _make_hit("MDN", "files/en-us/web/api/fetch_api/index.md", "Fetch API docs."),
    ]
    monkeypatch.setattr(retrieval, "_voyage", mock_voyage)
    monkeypatch.setattr(retrieval, "_qdrant", mock_qdrant)

    context, chunks = retrieval.retrieve_context_and_chunks("How do I verify a session?")

    assert context.startswith("--- RETRIEVED DOCS ---")
    assert "[Clerk - docs/authentication/sessions.mdx]" in context
    assert "Session info here." in context
    assert "[MDN - files/en-us/web/api/fetch_api/index.md]" in context
    assert "Fetch API docs." in context
    assert context.strip().endswith("--- END DOCS ---")
    assert chunks == [
        {"source": "Clerk", "path": "docs/authentication/sessions.mdx", "text": "Session info here.", "url": "https://clerk.com/docs/authentication/sessions"},
        {"source": "MDN", "path": "files/en-us/web/api/fetch_api/index.md", "text": "Fetch API docs.", "url": "https://developer.mozilla.org/en-US/docs/web/api/fetch_api"},
    ]


def test_retrieve_context_and_chunks_empty_when_no_hits(monkeypatch):
    """No hits — returns ("", []) rather than an empty formatted block."""
    mock_voyage = MagicMock()
    mock_voyage.embed.return_value.embeddings = [[0.1] * 512]
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = []
    monkeypatch.setattr(retrieval, "_voyage", mock_voyage)
    monkeypatch.setattr(retrieval, "_qdrant", mock_qdrant)

    assert retrieval.retrieve_context_and_chunks("some question") == ("", [])


# Tests for canonical_url function
def test_canonical_url_clerk_path():
    """canonical_url for Clerk path: docs/<rest>.mdx → https://clerk.com/docs/<rest>"""
    url = retrieval.canonical_url("Clerk", "docs/guides/sessions/session-tokens.mdx")
    assert url == "https://clerk.com/docs/guides/sessions/session-tokens"


def test_canonical_url_clerk_index_mdx():
    """canonical_url for Clerk index.mdx: drops the /index suffix."""
    url = retrieval.canonical_url("Clerk", "docs/guides/how-clerk-works/index.mdx")
    assert url == "https://clerk.com/docs/guides/how-clerk-works"


def test_canonical_url_mdn_path():
    """canonical_url for MDN path: files/en-us/<rest>/index.md → https://developer.mozilla.org/en-US/docs/<rest>"""
    url = retrieval.canonical_url("MDN", "files/en-us/web/api/fetch_api/index.md")
    assert url == "https://developer.mozilla.org/en-US/docs/web/api/fetch_api"


def test_canonical_url_unknown_source():
    """canonical_url for unknown source → None."""
    url = retrieval.canonical_url("UnknownSource", "docs/something.mdx")
    assert url is None


def test_canonical_url_nonmatching_path():
    """canonical_url for non-matching path pattern → None."""
    url = retrieval.canonical_url("Clerk", "something/else.txt")
    assert url is None


def test_retrieve_chunks_includes_url(monkeypatch):
    """retrieve_chunks results include 'url' field."""
    mock_voyage = MagicMock()
    mock_voyage.embed.return_value.embeddings = [[0.1] * 512]
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = [
        _make_hit("Clerk", "docs/guides/sessions/session-tokens.mdx", "Session info here."),
    ]
    monkeypatch.setattr(retrieval, "_voyage", mock_voyage)
    monkeypatch.setattr(retrieval, "_qdrant", mock_qdrant)

    chunks = retrieval.retrieve_chunks("How do I verify a session?")

    assert len(chunks) == 1
    assert "url" in chunks[0]
    assert chunks[0]["url"] == "https://clerk.com/docs/guides/sessions/session-tokens"


def test_retrieve_context_and_chunks_includes_url_header(monkeypatch):
    """Formatted context block includes URL: <url> under each header."""
    mock_voyage = MagicMock()
    mock_voyage.embed.return_value.embeddings = [[0.1] * 512]
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = [
        _make_hit("Clerk", "docs/guides/sessions/session-tokens.mdx", "Session info here."),
    ]
    monkeypatch.setattr(retrieval, "_voyage", mock_voyage)
    monkeypatch.setattr(retrieval, "_qdrant", mock_qdrant)

    context, chunks = retrieval.retrieve_context_and_chunks("How do I verify a session?")

    assert "URL: https://clerk.com/docs/guides/sessions/session-tokens" in context
    assert "[Clerk - docs/guides/sessions/session-tokens.mdx]" in context


def test_retrieve_context_and_chunks_omits_url_when_none(monkeypatch):
    """Formatted context block omits URL line when url is None."""
    mock_voyage = MagicMock()
    mock_voyage.embed.return_value.embeddings = [[0.1] * 512]
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = [
        _make_hit("UnknownSource", "docs/something.mdx", "Some info."),
    ]
    monkeypatch.setattr(retrieval, "_voyage", mock_voyage)
    monkeypatch.setattr(retrieval, "_qdrant", mock_qdrant)

    context, chunks = retrieval.retrieve_context_and_chunks("some question")

    # Should not have "URL: None" or "URL: " lines
    assert not any(line.startswith("URL:") for line in context.split("\n"))
    assert "[UnknownSource - docs/something.mdx]" in context


# Path safety tests: canonical_url must reject unsafe paths
def test_canonical_url_rejects_newline_injection():
    """canonical_url must return None for paths with newline characters."""
    url = retrieval.canonical_url("Clerk", "docs/auth\nmalicious.mdx")
    assert url is None


def test_canonical_url_rejects_carriage_return():
    """canonical_url must return None for paths with carriage returns."""
    url = retrieval.canonical_url("Clerk", "docs/auth\rmalicious.mdx")
    assert url is None


def test_canonical_url_rejects_parent_directory_traversal():
    """canonical_url must return None for paths containing '..'."""
    url = retrieval.canonical_url("Clerk", "docs/../../../etc/passwd.mdx")
    assert url is None


def test_canonical_url_rejects_question_mark():
    """canonical_url must return None for paths containing '?' (query string injection)."""
    url = retrieval.canonical_url("Clerk", "docs/auth?param=value.mdx")
    assert url is None


def test_canonical_url_rejects_hash():
    """canonical_url must return None for paths containing '#' (fragment injection)."""
    url = retrieval.canonical_url("Clerk", "docs/auth#section.mdx")
    assert url is None


def test_canonical_url_rejects_space():
    """canonical_url must return None for paths containing spaces."""
    url = retrieval.canonical_url("Clerk", "docs/auth space.mdx")
    assert url is None


def test_canonical_url_rejects_at_sign():
    """canonical_url must return None for paths containing '@' (email injection)."""
    url = retrieval.canonical_url("Clerk", "docs/auth@evil.mdx")
    assert url is None


def test_canonical_url_rejects_empty_segments():
    """canonical_url must return None for paths with empty segments (//)."""
    url = retrieval.canonical_url("Clerk", "docs//auth.mdx")
    assert url is None


def test_canonical_url_rejects_control_characters():
    """canonical_url must return None for paths with control characters."""
    url = retrieval.canonical_url("Clerk", "docs/auth\x00null.mdx")
    assert url is None


# Top-level index handling
def test_canonical_url_clerk_top_level_index():
    """canonical_url for Clerk top-level index: docs/index.mdx → https://clerk.com/docs"""
    url = retrieval.canonical_url("Clerk", "docs/index.mdx")
    assert url == "https://clerk.com/docs"


def test_canonical_url_mdn_top_level_index_returns_none():
    """canonical_url for MDN top-level index: files/en-us/index.md → None (empty rest)."""
    url = retrieval.canonical_url("MDN", "files/en-us/index.md")
    assert url is None


def test_canonical_url_clerk_nested_index_stripped():
    """canonical_url for Clerk nested index: docs/guides/index.mdx → https://clerk.com/docs/guides"""
    url = retrieval.canonical_url("Clerk", "docs/guides/index.mdx")
    assert url == "https://clerk.com/docs/guides"


# Case-insensitive source handling
def test_canonical_url_case_insensitive_clerk_lowercase():
    """canonical_url source is case-insensitive: 'clerk' should work."""
    url = retrieval.canonical_url("clerk", "docs/auth/sessions.mdx")
    assert url == "https://clerk.com/docs/auth/sessions"


def test_canonical_url_case_insensitive_mdn_uppercase():
    """canonical_url source is case-insensitive: 'MDN' should work."""
    url = retrieval.canonical_url("mdn", "files/en-us/web/api/fetch_api/index.md")
    assert url == "https://developer.mozilla.org/en-US/docs/web/api/fetch_api"


def test_canonical_url_case_sensitive_source_casing_preserved():
    """canonical_url output URLs use canonical casing (e.g., Mozilla retains lowercase)."""
    url = retrieval.canonical_url("mdn", "files/en-us/web/api/index.md")
    # MDN's own redirects use lowercase slug in the returned URL
    assert "developer.mozilla.org" in url and "en-US" in url


# None-safety test for retrieve_chunks
def test_retrieve_chunks_handles_null_repo_path(monkeypatch):
    """retrieve_chunks gracefully handles hit.payload.repo_path being None."""
    mock_voyage = MagicMock()
    mock_voyage.embed.return_value.embeddings = [[0.1] * 512]
    mock_qdrant = MagicMock()
    hit = MagicMock()
    hit.payload = {"source": "Clerk", "repo_path": None, "text": "Some text."}
    mock_qdrant.query_points.return_value.points = [hit]
    monkeypatch.setattr(retrieval, "_voyage", mock_voyage)
    monkeypatch.setattr(retrieval, "_qdrant", mock_qdrant)

    chunks = retrieval.retrieve_chunks("some question")

    assert len(chunks) == 1
    assert chunks[0]["path"] is None or chunks[0]["path"] == ""
    assert chunks[0]["url"] is None
    assert chunks[0]["text"] == "Some text."
    assert chunks[0]["source"] == "Clerk"


def test_retrieve_chunks_handles_null_source(monkeypatch):
    """retrieve_chunks gracefully handles hit.payload.source being None."""
    mock_voyage = MagicMock()
    mock_voyage.embed.return_value.embeddings = [[0.1] * 512]
    mock_qdrant = MagicMock()
    hit = MagicMock()
    hit.payload = {"source": None, "repo_path": "docs/auth.mdx", "text": "Some text."}
    mock_qdrant.query_points.return_value.points = [hit]
    monkeypatch.setattr(retrieval, "_voyage", mock_voyage)
    monkeypatch.setattr(retrieval, "_qdrant", mock_qdrant)

    chunks = retrieval.retrieve_chunks("some question")

    assert len(chunks) == 1
    assert chunks[0]["source"] is None or chunks[0]["source"] == ""
    assert chunks[0]["url"] is None


# Header injection hardening
def test_retrieve_context_and_chunks_sanitizes_newline_in_source(monkeypatch):
    """retrieve_context_and_chunks replaces \\n in source name with space for header safety."""
    mock_voyage = MagicMock()
    mock_voyage.embed.return_value.embeddings = [[0.1] * 512]
    mock_qdrant = MagicMock()
    hit = MagicMock()
    hit.payload = {"source": "Clerk\nEvil", "repo_path": "docs/auth.mdx", "text": "Safe text."}
    mock_qdrant.query_points.return_value.points = [hit]
    monkeypatch.setattr(retrieval, "_voyage", mock_voyage)
    monkeypatch.setattr(retrieval, "_qdrant", mock_qdrant)

    context, chunks = retrieval.retrieve_context_and_chunks("some question")

    # Newline should be replaced with space in the header
    assert "[Clerk Evil - docs/auth.mdx]" in context
    assert "[Clerk\nEvil" not in context


def test_retrieve_context_and_chunks_sanitizes_newline_in_path(monkeypatch):
    """retrieve_context_and_chunks replaces \\n in path with space for header safety."""
    mock_voyage = MagicMock()
    mock_voyage.embed.return_value.embeddings = [[0.1] * 512]
    mock_qdrant = MagicMock()
    hit = MagicMock()
    hit.payload = {"source": "Clerk", "repo_path": "docs/auth\nmalicious.mdx", "text": "Safe text."}
    mock_qdrant.query_points.return_value.points = [hit]
    monkeypatch.setattr(retrieval, "_voyage", mock_voyage)
    monkeypatch.setattr(retrieval, "_qdrant", mock_qdrant)

    context, chunks = retrieval.retrieve_context_and_chunks("some question")

    # Newline should be replaced with space in the header
    assert "[Clerk - docs/auth malicious.mdx]" in context
    assert "[Clerk - docs/auth\nmalicious.mdx]" not in context


def test_retrieve_context_and_chunks_sanitizes_carriage_return_in_source(monkeypatch):
    """retrieve_context_and_chunks replaces \\r in source name with space for header safety."""
    mock_voyage = MagicMock()
    mock_voyage.embed.return_value.embeddings = [[0.1] * 512]
    mock_qdrant = MagicMock()
    hit = MagicMock()
    hit.payload = {"source": "Clerk\rEvil", "repo_path": "docs/auth.mdx", "text": "Safe text."}
    mock_qdrant.query_points.return_value.points = [hit]
    monkeypatch.setattr(retrieval, "_voyage", mock_voyage)
    monkeypatch.setattr(retrieval, "_qdrant", mock_qdrant)

    context, chunks = retrieval.retrieve_context_and_chunks("some question")

    # Carriage return should be replaced with space in the header
    assert "[Clerk Evil - docs/auth.mdx]" in context
    assert "[Clerk\rEvil" not in context


def test_retrieve_context_and_chunks_sanitizes_carriage_return_in_path(monkeypatch):
    """retrieve_context_and_chunks replaces \\r in path with space for header safety."""
    mock_voyage = MagicMock()
    mock_voyage.embed.return_value.embeddings = [[0.1] * 512]
    mock_qdrant = MagicMock()
    hit = MagicMock()
    hit.payload = {"source": "Clerk", "repo_path": "docs/auth\rmalicious.mdx", "text": "Safe text."}
    mock_qdrant.query_points.return_value.points = [hit]
    monkeypatch.setattr(retrieval, "_voyage", mock_voyage)
    monkeypatch.setattr(retrieval, "_qdrant", mock_qdrant)

    context, chunks = retrieval.retrieve_context_and_chunks("some question")

    # Carriage return should be replaced with space in the header
    assert "[Clerk - docs/auth malicious.mdx]" in context
    assert "[Clerk - docs/auth\rmalicious.mdx]" not in context
