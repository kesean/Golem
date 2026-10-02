"""
tests/test_evals_rules.py — Tests for the five rule checks.

Covers:
- Each rule with one passing and one failing fixture
- Error short-circuiting behavior
- Retrieval passing when expectedSources is unset
"""

import pytest
from evals.models import EvalCase, RuleResults
from evals.rules import evaluate_rules, parse_product_tag


class TestParseProductTag:
    """Test product tag parsing."""

    def test_parse_valid_tag(self):
        """Parse a valid product tag from response."""
        response = "<product_tag>Authentication</product_tag>"
        assert parse_product_tag(response) == "Authentication"

    def test_parse_tag_with_whitespace(self):
        """Parse tag with surrounding whitespace."""
        response = "<product_tag>  Rate Limits  </product_tag>"
        assert parse_product_tag(response) == "Rate Limits"

    def test_parse_tag_case_insensitive(self):
        """Parse tag with different case."""
        response = "<PRODUCT_TAG>SDK</PRODUCT_TAG>"
        assert parse_product_tag(response) == "SDK"

    def test_parse_missing_tag(self):
        """Return None when tag is missing."""
        response = "<summary>No tag here</summary>"
        assert parse_product_tag(response) is None

    def test_parse_tag_with_multiline_content(self):
        """Parse tag even if content spans multiple lines."""
        response = "<product_tag>\nDEBUGGING\n</product_tag>"
        assert parse_product_tag(response) == "DEBUGGING"


class TestRuleCompleted:
    """Test the 'completed' rule: there is no error."""

    def test_completed_pass(self):
        """Rule passes when error is None."""
        case = EvalCase(
            id="test-1",
            question="Test question?",
            expected_product_tag="Authentication",
            key_points=["point1", "point2"],
            category="clerk-auth"
        )
        response = (
            "<product_tag>Authentication</product_tag>\n"
            "<summary>Test summary</summary>\n"
            "<root_cause>Test root cause</root_cause>\n"
            "<debug_steps>Step 1: test</debug_steps>\n"
            "<docs></docs>"
        )
        result = evaluate_rules(case, response, chunks=[], error=None)
        assert result.completed is True

    def test_completed_fail(self):
        """Rule fails when error is present."""
        case = EvalCase(
            id="test-2",
            question="Test question?",
            expected_product_tag="Authentication",
            key_points=["point1", "point2"],
            category="clerk-auth"
        )
        response = ""
        result = evaluate_rules(case, response, chunks=[], error="Connection timeout")
        assert result.completed is False


class TestRuleFormat:
    """Test the 'format' rule: all tags present and non-empty summary/root_cause."""

    def test_format_pass(self):
        """Rule passes with all tags present and non-empty summary/root_cause."""
        case = EvalCase(
            id="test-3",
            question="Test question?",
            expected_product_tag="Authentication",
            key_points=["point1", "point2"],
            category="clerk-auth"
        )
        response = (
            "<product_tag>Authentication</product_tag>\n"
            "<summary>This is a summary</summary>\n"
            "<root_cause>This is the root cause</root_cause>\n"
            "<debug_steps>Step 1: test\nStep 2: verify</debug_steps>\n"
            "<docs>https://example.com</docs>"
        )
        result = evaluate_rules(case, response, chunks=[], error=None)
        assert result.format is True

    def test_format_fail_missing_tag(self):
        """Rule fails when a tag is missing."""
        case = EvalCase(
            id="test-4",
            question="Test question?",
            expected_product_tag="Authentication",
            key_points=["point1", "point2"],
            category="clerk-auth"
        )
        response = (
            "<product_tag>Authentication</product_tag>\n"
            "<summary>This is a summary</summary>\n"
            "<root_cause>This is the root cause</root_cause>\n"
            "<docs>https://example.com</docs>"
            # Missing debug_steps
        )
        result = evaluate_rules(case, response, chunks=[], error=None)
        assert result.format is False

    def test_format_fail_empty_summary(self):
        """Rule fails when summary is empty."""
        case = EvalCase(
            id="test-5",
            question="Test question?",
            expected_product_tag="Authentication",
            key_points=["point1", "point2"],
            category="clerk-auth"
        )
        response = (
            "<product_tag>Authentication</product_tag>\n"
            "<summary></summary>\n"
            "<root_cause>This is the root cause</root_cause>\n"
            "<debug_steps>Step 1: test</debug_steps>\n"
            "<docs>https://example.com</docs>"
        )
        result = evaluate_rules(case, response, chunks=[], error=None)
        assert result.format is False

    def test_format_fail_empty_root_cause(self):
        """Rule fails when root_cause is empty."""
        case = EvalCase(
            id="test-6",
            question="Test question?",
            expected_product_tag="Authentication",
            key_points=["point1", "point2"],
            category="clerk-auth"
        )
        response = (
            "<product_tag>Authentication</product_tag>\n"
            "<summary>This is a summary</summary>\n"
            "<root_cause>   </root_cause>\n"
            "<debug_steps>Step 1: test</debug_steps>\n"
            "<docs>https://example.com</docs>"
        )
        result = evaluate_rules(case, response, chunks=[], error=None)
        assert result.format is False

    def test_format_pass_case_insensitive(self):
        """Rule passes with different tag case."""
        case = EvalCase(
            id="test-7",
            question="Test question?",
            expected_product_tag="Authentication",
            key_points=["point1", "point2"],
            category="clerk-auth"
        )
        response = (
            "<PRODUCT_TAG>Authentication</PRODUCT_TAG>\n"
            "<SUMMARY>This is a summary</SUMMARY>\n"
            "<ROOT_CAUSE>This is the root cause</ROOT_CAUSE>\n"
            "<DEBUG_STEPS>Step 1: test</DEBUG_STEPS>\n"
            "<DOCS>https://example.com</DOCS>"
        )
        result = evaluate_rules(case, response, chunks=[], error=None)
        assert result.format is True


class TestRuleProductTag:
    """Test the 'productTag' rule: parsed tag equals expectedProductTag."""

    def test_product_tag_pass(self):
        """Rule passes when parsed tag matches expected."""
        case = EvalCase(
            id="test-8",
            question="Test question?",
            expected_product_tag="CORS",
            key_points=["point1", "point2"],
            category="web-platform"
        )
        response = (
            "<product_tag>CORS</product_tag>\n"
            "<summary>Summary</summary>\n"
            "<root_cause>Root cause</root_cause>\n"
            "<debug_steps>Step 1: test</debug_steps>\n"
            "<docs></docs>"
        )
        result = evaluate_rules(case, response, chunks=[], error=None)
        assert result.product_tag is True

    def test_product_tag_fail_mismatch(self):
        """Rule fails when parsed tag doesn't match expected."""
        case = EvalCase(
            id="test-9",
            question="Test question?",
            expected_product_tag="Authentication",
            key_points=["point1", "point2"],
            category="clerk-auth"
        )
        response = (
            "<product_tag>CORS</product_tag>\n"
            "<summary>Summary</summary>\n"
            "<root_cause>Root cause</root_cause>\n"
            "<debug_steps>Step 1: test</debug_steps>\n"
            "<docs></docs>"
        )
        result = evaluate_rules(case, response, chunks=[], error=None)
        assert result.product_tag is False

    def test_product_tag_fail_missing(self):
        """Rule fails when tag is missing."""
        case = EvalCase(
            id="test-10",
            question="Test question?",
            expected_product_tag="Authentication",
            key_points=["point1", "point2"],
            category="clerk-auth"
        )
        response = (
            "<summary>Summary</summary>\n"
            "<root_cause>Root cause</root_cause>\n"
            "<debug_steps>Step 1: test</debug_steps>\n"
            "<docs></docs>"
        )
        result = evaluate_rules(case, response, chunks=[], error=None)
        assert result.product_tag is False


class TestRuleCitations:
    """Test the 'citations' rule: no unretrieved doc URLs."""

    def test_citations_pass(self):
        """Rule passes when all cited URLs are retrieved."""
        case = EvalCase(
            id="test-11",
            question="Test question?",
            expected_product_tag="Authentication",
            key_points=["point1", "point2"],
            category="clerk-auth"
        )
        response = (
            "<product_tag>Authentication</product_tag>\n"
            "<summary>Summary</summary>\n"
            "<root_cause>Root cause</root_cause>\n"
            "<debug_steps>Step 1: test</debug_steps>\n"
            "<docs>Clerk Auth: https://docs.clerk.com/auth</docs>"
        )
        chunks = [
            {"source": "clerk", "path": "/auth", "text": "...", "url": "https://docs.clerk.com/auth"}
        ]
        result = evaluate_rules(case, response, chunks=chunks, error=None)
        assert result.citations is True

    def test_citations_pass_empty_docs(self):
        """Rule passes when there are no citations."""
        case = EvalCase(
            id="test-12",
            question="Test question?",
            expected_product_tag="Authentication",
            key_points=["point1", "point2"],
            category="clerk-auth"
        )
        response = (
            "<product_tag>Authentication</product_tag>\n"
            "<summary>Summary</summary>\n"
            "<root_cause>Root cause</root_cause>\n"
            "<debug_steps>Step 1: test</debug_steps>\n"
            "<docs></docs>"
        )
        result = evaluate_rules(case, response, chunks=[], error=None)
        assert result.citations is True

    def test_citations_fail_unretrieved(self):
        """Rule fails when a cited URL is not retrieved."""
        case = EvalCase(
            id="test-13",
            question="Test question?",
            expected_product_tag="Authentication",
            key_points=["point1", "point2"],
            category="clerk-auth"
        )
        response = (
            "<product_tag>Authentication</product_tag>\n"
            "<summary>Summary</summary>\n"
            "<root_cause>Root cause</root_cause>\n"
            "<debug_steps>Step 1: test</debug_steps>\n"
            "<docs>\n"
            "Clerk Auth: https://docs.clerk.com/auth\n"
            "MDN Fetch: https://developer.mozilla.org/fetch\n"
            "</docs>"
        )
        chunks = [
            {"source": "clerk", "path": "/auth", "text": "...", "url": "https://docs.clerk.com/auth"}
            # Missing MDN Fetch URL
        ]
        result = evaluate_rules(case, response, chunks=chunks, error=None)
        assert result.citations is False


class TestRuleRetrieval:
    """Test the 'retrieval' rule: when expectedSources is set, at least one chunk from each source."""

    def test_retrieval_pass_with_expected_sources(self):
        """Rule passes when all expected sources are retrieved."""
        case = EvalCase(
            id="test-14",
            question="Test question?",
            expected_product_tag="Authentication",
            key_points=["point1", "point2"],
            expected_sources=["clerk", "mdn"],
            category="clerk-auth"
        )
        response = (
            "<product_tag>Authentication</product_tag>\n"
            "<summary>Summary</summary>\n"
            "<root_cause>Root cause</root_cause>\n"
            "<debug_steps>Step 1: test</debug_steps>\n"
            "<docs></docs>"
        )
        chunks = [
            {"source": "clerk", "path": "/auth", "text": "...", "url": "https://docs.clerk.com/auth"},
            {"source": "mdn", "path": "/fetch", "text": "...", "url": "https://developer.mozilla.org/fetch"}
        ]
        result = evaluate_rules(case, response, chunks=chunks, error=None)
        assert result.retrieval is True

    def test_retrieval_pass_unset_expected_sources(self):
        """Rule passes when expectedSources is None (unset)."""
        case = EvalCase(
            id="test-15",
            question="Test question?",
            expected_product_tag="Other",
            key_points=["point1", "point2"],
            expected_sources=None,  # Unset
            category="off-topic"
        )
        response = (
            "<product_tag>Other</product_tag>\n"
            "<summary>Summary</summary>\n"
            "<root_cause>Root cause</root_cause>\n"
            "<debug_steps>Step 1: test</debug_steps>\n"
            "<docs></docs>"
        )
        result = evaluate_rules(case, response, chunks=[], error=None)
        assert result.retrieval is True

    def test_retrieval_fail_missing_source(self):
        """Rule fails when an expected source is missing."""
        case = EvalCase(
            id="test-16",
            question="Test question?",
            expected_product_tag="Authentication",
            key_points=["point1", "point2"],
            expected_sources=["clerk", "mdn"],
            category="clerk-auth"
        )
        response = (
            "<product_tag>Authentication</product_tag>\n"
            "<summary>Summary</summary>\n"
            "<root_cause>Root cause</root_cause>\n"
            "<debug_steps>Step 1: test</debug_steps>\n"
            "<docs></docs>"
        )
        chunks = [
            {"source": "clerk", "path": "/auth", "text": "...", "url": "https://docs.clerk.com/auth"}
            # Missing mdn source
        ]
        result = evaluate_rules(case, response, chunks=chunks, error=None)
        assert result.retrieval is False


class TestErrorHandling:
    """Test that error short-circuits all rules except completed."""

    def test_error_short_circuits_all_rules(self):
        """When error is present, completed is False and all other rules are False."""
        case = EvalCase(
            id="test-17",
            question="Test question?",
            expected_product_tag="Authentication",
            key_points=["point1", "point2"],
            expected_sources=["clerk"],
            category="clerk-auth"
        )
        # Even with a perfect response, error should make all rules False
        response = (
            "<product_tag>Authentication</product_tag>\n"
            "<summary>Summary</summary>\n"
            "<root_cause>Root cause</root_cause>\n"
            "<debug_steps>Step 1: test</debug_steps>\n"
            "<docs></docs>"
        )
        chunks = [{"source": "clerk", "path": "/auth", "text": "...", "url": "https://docs.clerk.com/auth"}]

        result = evaluate_rules(case, response, chunks=chunks, error="API call failed")

        assert result.completed is False
        assert result.format is False
        assert result.product_tag is False
        assert result.citations is False
        assert result.retrieval is False

    def test_error_with_empty_response(self):
        """Error handling with empty response."""
        case = EvalCase(
            id="test-18",
            question="Test question?",
            expected_product_tag="Authentication",
            key_points=["point1", "point2"],
            category="clerk-auth"
        )
        result = evaluate_rules(case, "", chunks=[], error="Timeout")

        assert result.completed is False
        assert result.format is False
        assert result.product_tag is False
        assert result.citations is False
        assert result.retrieval is False


class TestIntegration:
    """Integration tests for complex scenarios."""

    def test_all_rules_pass(self):
        """All rules pass in a good response."""
        case = EvalCase(
            id="test-19",
            question="How do I authenticate?",
            expected_product_tag="Authentication",
            key_points=["Use Clerk SDK", "Set environment variables"],
            expected_sources=["clerk"],
            category="clerk-auth"
        )
        response = (
            "<product_tag>Authentication</product_tag>\n"
            "<summary>Use the Clerk SDK to authenticate your users.</summary>\n"
            "<root_cause>You need to set up the Clerk environment variables.</root_cause>\n"
            "<debug_steps>\n"
            "Step 1: Install the Clerk SDK\n"
            "Step 2: Set CLERK_API_KEY\n"
            "Step 3: Initialize Clerk in your app\n"
            "</debug_steps>\n"
            "<docs>Clerk Auth: https://docs.clerk.com/auth</docs>"
        )
        chunks = [
            {"source": "clerk", "path": "/auth", "text": "Auth guide...", "url": "https://docs.clerk.com/auth"}
        ]

        result = evaluate_rules(case, response, chunks=chunks, error=None)

        assert result.completed is True
        assert result.format is True
        assert result.product_tag is True
        assert result.citations is True
        assert result.retrieval is True

    def test_multiple_failures(self):
        """Multiple rules fail in a poor response."""
        case = EvalCase(
            id="test-20",
            question="How do I authenticate?",
            expected_product_tag="Authentication",
            key_points=["Use Clerk SDK", "Set environment variables"],
            expected_sources=["clerk", "mdn"],
            category="clerk-auth"
        )
        response = (
            "<product_tag>CORS</product_tag>\n"  # Wrong tag
            "<summary></summary>\n"  # Empty summary
            "<root_cause>Cause</root_cause>\n"
            "<debug_steps>Step 1: test</debug_steps>\n"
            "<docs>\n"
            "Missing URL: https://example.com/missing\n"  # Unretrieved URL
            "</docs>"
        )
        chunks = [
            {"source": "clerk", "path": "/auth", "text": "...", "url": "https://docs.clerk.com/auth"}
            # Missing mdn source
        ]

        result = evaluate_rules(case, response, chunks=chunks, error=None)

        assert result.completed is True  # No error
        assert result.format is False  # Empty summary
        assert result.product_tag is False  # Wrong tag
        assert result.citations is False  # Unretrieved URL
        assert result.retrieval is False  # Missing mdn source
