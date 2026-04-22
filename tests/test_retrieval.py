"""test_retrieval.py — Unit tests for retrieval.py."""
from unittest.mock import MagicMock
import retrieval


def _make_hit(source, path, text):
    hit = MagicMock()
    hit.payload = {"source": source, "repo_path": path, "text": text}
    return hit


def test_returns_formatted_block_when_results_found(monkeypatch):
    """Happy path: Qdrant returns hits, function returns a formatted doc block."""
    mock_voyage = MagicMock()
    mock_voyage.embed.return_value.embeddings = [[0.1] * 512]
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = [
        _make_hit("Clerk", "docs/authentication/sessions.mdx", "Session info here."),
        _make_hit("MDN", "files/en-us/web/api/fetch_api/index.md", "Fetch API docs."),
    ]
    monkeypatch.setattr(retrieval, "_voyage", mock_voyage)
    monkeypatch.setattr(retrieval, "_qdrant", mock_qdrant)

    result = retrieval.retrieve_context("How do I verify a session?")

    assert result.startswith("--- RETRIEVED DOCS ---")
    assert "[Clerk - docs/authentication/sessions.mdx]" in result
    assert "Session info here." in result
    assert "[MDN - files/en-us/web/api/fetch_api/index.md]" in result
    assert "Fetch API docs." in result
    assert result.strip().endswith("--- END DOCS ---")


def test_returns_empty_string_when_no_results(monkeypatch):
    """Qdrant returns empty list — function returns empty string."""
    mock_voyage = MagicMock()
    mock_voyage.embed.return_value.embeddings = [[0.1] * 512]
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = []
    monkeypatch.setattr(retrieval, "_voyage", mock_voyage)
    monkeypatch.setattr(retrieval, "_qdrant", mock_qdrant)

    assert retrieval.retrieve_context("some question") == ""


def test_returns_empty_string_when_qdrant_client_is_none(monkeypatch):
    """_qdrant is None (QDRANT_URL missing at startup) — returns "" without raising."""
    monkeypatch.setattr(retrieval, "_qdrant", None)
    monkeypatch.setattr(retrieval, "_voyage", MagicMock())

    assert retrieval.retrieve_context("some question") == ""


def test_returns_empty_string_when_voyage_client_is_none(monkeypatch):
    """_voyage is None (VOYAGE_API_KEY missing at startup) — returns "" without raising."""
    monkeypatch.setattr(retrieval, "_qdrant", MagicMock())
    monkeypatch.setattr(retrieval, "_voyage", None)

    assert retrieval.retrieve_context("some question") == ""


def test_returns_empty_string_when_voyage_raises(monkeypatch):
    """Voyage API call fails — returns empty string, does not raise."""
    mock_voyage = MagicMock()
    mock_voyage.embed.side_effect = Exception("Voyage API error")
    monkeypatch.setattr(retrieval, "_voyage", mock_voyage)
    monkeypatch.setattr(retrieval, "_qdrant", MagicMock())

    assert retrieval.retrieve_context("some question") == ""


def test_returns_empty_string_when_qdrant_raises(monkeypatch):
    """Qdrant query fails — returns empty string, does not raise."""
    mock_voyage = MagicMock()
    mock_voyage.embed.return_value.embeddings = [[0.1] * 512]
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.side_effect = Exception("Qdrant connection error")
    monkeypatch.setattr(retrieval, "_voyage", mock_voyage)
    monkeypatch.setattr(retrieval, "_qdrant", mock_qdrant)

    assert retrieval.retrieve_context("some question") == ""


def test_source_filter_passed_to_qdrant_when_provided(monkeypatch):
    """When source='clerk' is passed, query_points is called with a filter on source == 'clerk'."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    mock_voyage = MagicMock()
    mock_voyage.embed.return_value.embeddings = [[0.1] * 512]
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = []
    monkeypatch.setattr(retrieval, "_voyage", mock_voyage)
    monkeypatch.setattr(retrieval, "_qdrant", mock_qdrant)

    retrieval.retrieve_context("How do I verify a session?", source="clerk")

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

    retrieval.retrieve_context("some question", source=None)

    call_kwargs = mock_qdrant.query_points.call_args.kwargs
    assert call_kwargs.get("query_filter") is None
