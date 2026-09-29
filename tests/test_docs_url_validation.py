"""test_docs_url_validation.py — Unit tests for find_unretrieved_doc_urls."""

import pytest


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_docs_block():
    """Response with no <docs> block returns empty list."""
    from chat import find_unretrieved_doc_urls

    response = "<summary>Some answer</summary><root_cause>Some cause</root_cause>"
    chunks = []
    result = find_unretrieved_doc_urls(response, chunks)
    assert result == []


def test_all_cited_retrieved():
    """All URLs in docs block are found in chunks returns empty list."""
    from chat import find_unretrieved_doc_urls

    response = """<summary>Answer</summary>
<docs>
My Doc: https://example.com/docs
Another: https://example.com/other
</docs>"""
    chunks = [
        {"url": "https://example.com/docs"},
        {"url": "https://example.com/other"},
    ]
    result = find_unretrieved_doc_urls(response, chunks)
    assert result == []


def test_one_unretrieved():
    """One URL in docs not found in chunks is returned."""
    from chat import find_unretrieved_doc_urls

    response = """<summary>Answer</summary>
<docs>
My Doc: https://example.com/docs
Missing: https://example.com/missing
</docs>"""
    chunks = [
        {"url": "https://example.com/docs"},
    ]
    result = find_unretrieved_doc_urls(response, chunks)
    assert result == ["https://example.com/missing"]


def test_empty_chunks():
    """Empty chunks list means all docs URLs are unretrieved."""
    from chat import find_unretrieved_doc_urls

    response = """<summary>Answer</summary>
<docs>
Doc 1: https://example.com/doc1
Doc 2: https://example.com/doc2
</docs>"""
    chunks = []
    result = find_unretrieved_doc_urls(response, chunks)
    assert set(result) == {"https://example.com/doc1", "https://example.com/doc2"}


def test_trailing_slash_normalization():
    """URLs that differ only in trailing slash are considered the same."""
    from chat import find_unretrieved_doc_urls

    response = """<summary>Answer</summary>
<docs>
Doc: https://example.com/docs/
</docs>"""
    chunks = [
        {"url": "https://example.com/docs"},
    ]
    result = find_unretrieved_doc_urls(response, chunks)
    assert result == []


def test_trailing_slash_normalization_reversed():
    """URLs that differ only in trailing slash are considered the same (chunk has trailing slash)."""
    from chat import find_unretrieved_doc_urls

    response = """<summary>Answer</summary>
<docs>
Doc: https://example.com/docs
</docs>"""
    chunks = [
        {"url": "https://example.com/docs/"},
    ]
    result = find_unretrieved_doc_urls(response, chunks)
    assert result == []


def test_none_chunks():
    """None chunks are handled safely."""
    from chat import find_unretrieved_doc_urls

    response = """<summary>Answer</summary>
<docs>
Doc: https://example.com/docs
</docs>"""
    result = find_unretrieved_doc_urls(response, None)
    assert result == ["https://example.com/docs"]


def test_chunks_with_none_url():
    """Chunks with None url value are handled safely."""
    from chat import find_unretrieved_doc_urls

    response = """<summary>Answer</summary>
<docs>
Doc: https://example.com/docs
</docs>"""
    chunks = [
        {"url": None},
    ]
    result = find_unretrieved_doc_urls(response, chunks)
    assert result == ["https://example.com/docs"]


def test_empty_docs_block():
    """Empty <docs></docs> block returns empty list."""
    from chat import find_unretrieved_doc_urls

    response = """<summary>Answer</summary>
<docs>
</docs>"""
    chunks = []
    result = find_unretrieved_doc_urls(response, chunks)
    assert result == []


def test_malformed_doc_lines():
    """Lines without colons or URLs are skipped."""
    from chat import find_unretrieved_doc_urls

    response = """<summary>Answer</summary>
<docs>
Doc: https://example.com/docs
Just some text without URL
Another: https://example.com/other
</docs>"""
    chunks = []
    result = find_unretrieved_doc_urls(response, chunks)
    assert set(result) == {"https://example.com/docs", "https://example.com/other"}


def test_multiple_urls_in_one_line():
    """Multiple URLs in one line are extracted."""
    from chat import find_unretrieved_doc_urls

    response = """<summary>Answer</summary>
<docs>
Docs: https://example.com/docs https://example.com/other
</docs>"""
    chunks = []
    result = find_unretrieved_doc_urls(response, chunks)
    # Should extract both URLs from the line
    assert set(result) == {"https://example.com/docs", "https://example.com/other"}


def test_http_not_https():
    """URLs with http scheme are also extracted."""
    from chat import find_unretrieved_doc_urls

    response = """<summary>Answer</summary>
<docs>
Doc: http://example.com/docs
</docs>"""
    chunks = []
    result = find_unretrieved_doc_urls(response, chunks)
    assert result == ["http://example.com/docs"]


def test_multiple_docs_blocks():
    """Multiple <docs> blocks are all processed."""
    from chat import find_unretrieved_doc_urls

    response = """<summary>Answer</summary>
<docs>
Doc 1: https://example.com/doc1
</docs>
<docs>
Doc 2: https://example.com/doc2
</docs>"""
    chunks = []
    result = find_unretrieved_doc_urls(response, chunks)
    assert set(result) == {"https://example.com/doc1", "https://example.com/doc2"}


def test_url_with_query_params():
    """URLs with query parameters are correctly identified."""
    from chat import find_unretrieved_doc_urls

    response = """<summary>Answer</summary>
<docs>
Doc: https://example.com/docs?page=1&sort=name
</docs>"""
    chunks = [
        {"url": "https://example.com/docs?page=1&sort=name"},
    ]
    result = find_unretrieved_doc_urls(response, chunks)
    assert result == []


def test_deduplication():
    """Same URL appearing multiple times is returned only once."""
    from chat import find_unretrieved_doc_urls

    response = """<summary>Answer</summary>
<docs>
Doc 1: https://example.com/docs
Doc 2: https://example.com/docs
</docs>"""
    chunks = []
    result = find_unretrieved_doc_urls(response, chunks)
    assert result == ["https://example.com/docs"]


def test_markdown_link_format():
    """Markdown link format [label](url) is handled."""
    from chat import find_unretrieved_doc_urls

    response = """<summary>Answer</summary>
<docs>
[My Doc](https://example.com/docs)
</docs>"""
    chunks = []
    result = find_unretrieved_doc_urls(response, chunks)
    assert result == ["https://example.com/docs"]


def test_mixed_formats():
    """Mix of different doc link formats are handled."""
    from chat import find_unretrieved_doc_urls

    response = """<summary>Answer</summary>
<docs>
Doc 1: https://example.com/doc1
[Doc 2](https://example.com/doc2)
Another Doc: https://example.com/doc3
</docs>"""
    chunks = [
        {"url": "https://example.com/doc1"},
    ]
    result = find_unretrieved_doc_urls(response, chunks)
    assert set(result) == {"https://example.com/doc2", "https://example.com/doc3"}
