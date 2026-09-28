"""test_retrieval.py — Unit tests for retrieval.py."""
from unittest.mock import MagicMock
import retrieval


def _make_hit(source, path, text):
    hit = MagicMock()
    hit.payload = {"source": source, "repo_path": path, "text": text}
    return hit


def test_retrieve_chunks_returns_structured_hits(monkeypatch):
    """retrieve_chunks returns dicts with source/path/text, most relevant first."""
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
        {"source": "Clerk", "path": "docs/authentication/sessions.mdx", "text": "Session info here."},
        {"source": "MDN", "path": "files/en-us/web/api/fetch_api/index.md", "text": "Fetch API docs."},
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
        {"source": "Clerk", "path": "docs/authentication/sessions.mdx", "text": "Session info here."},
        {"source": "MDN", "path": "files/en-us/web/api/fetch_api/index.md", "text": "Fetch API docs."},
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
