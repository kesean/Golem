"""
Tests for the evaluation grader (judge_case function).
Covers all error paths, retries, and API contract.
"""

import json
import logging
import os

import httpx
import pytest

from evals.judge import judge_case
from evals.models import EvalCase, JudgeVerdict


def make_api_response(content: str, status_code: int = 200) -> httpx.Response:
    """Create a proper httpx.Response for testing."""
    response_data = {
        "choices": [
            {
                "message": {
                    "content": content,
                }
            }
        ]
    }
    return httpx.Response(status_code, content=json.dumps(response_data))


@pytest.fixture
def sample_case():
    """A sample evaluation case for testing."""
    return EvalCase(
        id="test-case-001",
        question="How do I authenticate with Clerk?",
        expected_product_tag="Authentication",
        key_points=[
            "Use ClerkProvider to wrap your app",
            "useAuth() hook provides currentUser",
        ],
        category="clerk-auth",
    )


@pytest.fixture
def sample_chunks():
    """Sample retrieved document chunks."""
    return [
        {
            "source": "clerk",
            "path": "/docs/auth",
            "text": "ClerkProvider wraps your entire application and provides auth context.",
            "url": "https://clerk.com/docs",
        },
        {
            "source": "clerk",
            "path": "/docs/hooks",
            "text": "The useAuth() hook returns currentUser, auth object, and more.",
            "url": "https://clerk.com/docs/hooks",
        },
    ]


@pytest.fixture
def sample_response():
    """Sample response from Golem."""
    return """<product_tag>Authentication</product_tag>
<summary>Use ClerkProvider and useAuth() to authenticate</summary>
<root_cause>Clerk requires setup at app root level</root_cause>
<debug_steps>1. Install @clerk/react 2. Wrap app with ClerkProvider</debug_steps>
<docs>https://clerk.com/docs</docs>"""


@pytest.fixture
def valid_verdict_json():
    """Valid verdict JSON response."""
    return json.dumps({
        "groundedness": 4,
        "coverage": 3,
        "keyPointsMissed": ["Mention of useAuth() was brief"],
        "reason": "The answer correctly explains ClerkProvider setup. Coverage of useAuth() could be more detailed.",
    })


class TestJudgeCaseValid:
    """Test valid grading scenarios."""

    def test_valid_verdict_success(self, sample_case, sample_chunks, sample_response, valid_verdict_json):
        """Test that a valid verdict is returned successfully."""
        mock_response = make_api_response(valid_verdict_json)
        mock_transport = httpx.MockTransport(lambda req: mock_response)

        with httpx.Client(transport=mock_transport) as client:
            verdict, error = judge_case(sample_case, sample_response, sample_chunks, client=client)

        assert error is None
        assert verdict is not None
        assert verdict.groundedness == 4
        assert verdict.coverage == 3
        assert isinstance(verdict.key_points_missed, list)
        assert "useAuth()" in verdict.key_points_missed[0]
        assert isinstance(verdict.reason, str)



class TestJudgeCaseRetry:
    """Test retry logic."""

    def test_invalid_then_valid_retry(self, sample_case, sample_chunks, sample_response, valid_verdict_json):
        """Test that invalid JSON triggers a retry and succeeds on second attempt."""
        call_count = [0]

        def handler(req):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: invalid JSON
                return make_api_response("not valid json")
            else:
                # Second call: valid JSON
                return make_api_response(valid_verdict_json)

        mock_transport = httpx.MockTransport(handler)

        with httpx.Client(transport=mock_transport) as client:
            verdict, error = judge_case(sample_case, sample_response, sample_chunks, client=client)

        assert error is None
        assert verdict is not None
        assert call_count[0] == 2
        assert verdict.groundedness == 4

    def test_invalid_twice_returns_error(self, sample_case, sample_chunks, sample_response):
        """Test that two invalid responses return invalid_output error."""
        def handler(req):
            return make_api_response("not valid json")

        mock_transport = httpx.MockTransport(handler)

        with httpx.Client(transport=mock_transport) as client:
            verdict, error = judge_case(sample_case, sample_response, sample_chunks, client=client)

        assert verdict is None
        assert error == "invalid_output"


class TestJudgeCaseValidation:
    """Test Pydantic validation scenarios."""

    def test_out_of_range_score_fails_validation(self, sample_case, sample_chunks, sample_response):
        """Test that out-of-range scores (e.g., 6) fail validation."""
        invalid_json = json.dumps({
            "groundedness": 6,  # Invalid: must be 1-5
            "coverage": 3,
            "keyPointsMissed": [],
            "reason": "Invalid score",
        })

        def handler(req):
            return make_api_response(invalid_json)

        mock_transport = httpx.MockTransport(handler)

        with httpx.Client(transport=mock_transport) as client:
            verdict, error = judge_case(sample_case, sample_response, sample_chunks, client=client)

        assert verdict is None
        assert error == "invalid_output"

    def test_missing_required_field_fails_validation(self, sample_case, sample_chunks, sample_response):
        """Test that missing required fields fail validation."""
        invalid_json = json.dumps({
            "groundedness": 4,
            # Missing coverage, keyPointsMissed, reason
        })

        def handler(req):
            return make_api_response(invalid_json)

        mock_transport = httpx.MockTransport(handler)

        with httpx.Client(transport=mock_transport) as client:
            verdict, error = judge_case(sample_case, sample_response, sample_chunks, client=client)

        assert verdict is None
        assert error == "invalid_output"


class TestJudgeCaseErrors:
    """Test error handling."""

    def test_http_500_error(self, sample_case, sample_chunks, sample_response):
        """Test that HTTP 500 returns http_error."""
        def handler(req):
            return make_api_response("error", status_code=500)

        mock_transport = httpx.MockTransport(handler)

        with httpx.Client(transport=mock_transport) as client:
            verdict, error = judge_case(sample_case, sample_response, sample_chunks, client=client)

        assert verdict is None
        assert error == "http_error: 500"

    def test_http_401_error(self, sample_case, sample_chunks, sample_response):
        """Test that HTTP 401 returns http_error."""
        def handler(req):
            return make_api_response("error", status_code=401)

        mock_transport = httpx.MockTransport(handler)

        with httpx.Client(transport=mock_transport) as client:
            verdict, error = judge_case(sample_case, sample_response, sample_chunks, client=client)

        assert verdict is None
        assert error == "http_error: 401"

    def test_request_error(self, sample_case, sample_chunks, sample_response):
        """Test that request errors are caught."""
        def handler(req):
            raise httpx.RequestError("Network error")

        mock_transport = httpx.MockTransport(handler)

        with httpx.Client(transport=mock_transport) as client:
            verdict, error = judge_case(sample_case, sample_response, sample_chunks, client=client)

        assert verdict is None
        assert error == "http_error: RequestError"

    def test_missing_api_key(self, sample_case, sample_chunks, sample_response, monkeypatch):
        """Test that missing API key returns missing_api_key error without making request."""
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

        def handler(req):
            raise AssertionError("Should not make request without API key")

        mock_transport = httpx.MockTransport(handler)

        with httpx.Client(transport=mock_transport) as client:
            verdict, error = judge_case(sample_case, sample_response, sample_chunks, client=client)

        assert verdict is None
        assert error == "missing_api_key"


class TestJudgeCaseRequestBody:
    """Test that request body contains expected data."""

    def test_request_contains_chunk_texts(self, sample_case, sample_chunks, sample_response, valid_verdict_json):
        """Test that request body includes chunk texts."""
        captured_request = []

        def handler(req):
            captured_request.append(req)
            return make_api_response(valid_verdict_json)

        mock_transport = httpx.MockTransport(handler)

        with httpx.Client(transport=mock_transport) as client:
            judge_case(sample_case, sample_response, sample_chunks, client=client)

        assert len(captured_request) > 0
        request = captured_request[0]
        body = request.content.decode() if isinstance(request.content, bytes) else request.content

        # Check that chunk texts are in the body
        assert "ClerkProvider wraps your entire application" in body
        assert "useAuth() hook returns currentUser" in body

    def test_request_contains_key_points(self, sample_case, sample_chunks, sample_response, valid_verdict_json):
        """Test that request body includes key points."""
        captured_request = []

        def handler(req):
            captured_request.append(req)
            return make_api_response(valid_verdict_json)

        mock_transport = httpx.MockTransport(handler)

        with httpx.Client(transport=mock_transport) as client:
            judge_case(sample_case, sample_response, sample_chunks, client=client)

        assert len(captured_request) > 0
        request = captured_request[0]
        body = request.content.decode() if isinstance(request.content, bytes) else request.content

        # Check that key points are in the body
        assert "Use ClerkProvider to wrap your app" in body
        assert "useAuth() hook provides currentUser" in body

    def test_request_contains_question(self, sample_case, sample_chunks, sample_response, valid_verdict_json):
        """Test that request body includes the question."""
        captured_request = []

        def handler(req):
            captured_request.append(req)
            return make_api_response(valid_verdict_json)

        mock_transport = httpx.MockTransport(handler)

        with httpx.Client(transport=mock_transport) as client:
            judge_case(sample_case, sample_response, sample_chunks, client=client)

        assert len(captured_request) > 0
        request = captured_request[0]
        body = request.content.decode() if isinstance(request.content, bytes) else request.content

        # Check that question is in the body
        assert sample_case.question in body


class TestJudgeCaseSecurity:
    """Test security aspects."""

    def test_api_key_not_in_error_string(self, sample_case, sample_chunks, sample_response, monkeypatch):
        """Test that API key never appears in error strings."""
        api_key = "sk-test-secret-key-12345"
        monkeypatch.setenv("DEEPSEEK_API_KEY", api_key)

        # Simulate an HTTP error
        def handler(req):
            return make_api_response("error", status_code=500)

        mock_transport = httpx.MockTransport(handler)

        with httpx.Client(transport=mock_transport) as client:
            verdict, error = judge_case(sample_case, sample_response, sample_chunks, client=client)

        assert error is not None
        assert api_key not in error
        assert "secret" not in error.lower()

    def test_api_key_not_in_logs(self, sample_case, sample_chunks, sample_response, monkeypatch, caplog):
        """Test that API key is not logged."""
        api_key = "sk-test-secret-key-12345"
        monkeypatch.setenv("DEEPSEEK_API_KEY", api_key)

        def handler(req):
            return make_api_response("error", status_code=500)

        mock_transport = httpx.MockTransport(handler)

        with caplog.at_level(logging.DEBUG):
            with httpx.Client(transport=mock_transport) as client:
                judge_case(sample_case, sample_response, sample_chunks, client=client)

        # Check logs for the API key
        log_text = caplog.text
        assert api_key not in log_text


class TestJudgeCaseIntegration:
    """Integration tests."""

    def test_uses_correct_model_and_base_url(self, sample_case, sample_chunks, sample_response, valid_verdict_json, monkeypatch):
        """Test that the correct model and base URL are used in requests."""
        monkeypatch.setenv("JUDGE_MODEL", "custom-model")
        monkeypatch.setenv("JUDGE_BASE_URL", "https://custom.api.com")

        # Reload the module to pick up new env vars
        import importlib
        import evals.judge
        importlib.reload(evals.judge)
        from evals.judge import judge_case as judge_case_reloaded

        captured_requests = []

        def handler(req):
            captured_requests.append(req)
            return make_api_response(valid_verdict_json)

        mock_transport = httpx.MockTransport(handler)

        with httpx.Client(transport=mock_transport) as client:
            judge_case_reloaded(sample_case, sample_response, sample_chunks, client=client)

        assert len(captured_requests) > 0
        request = captured_requests[0]

        # Check URL contains custom base
        assert "custom.api.com" in str(request.url)

        # Check model in payload
        body = request.content.decode() if isinstance(request.content, bytes) else request.content
        assert "custom-model" in body

    def test_authorization_header_format(self, sample_case, sample_chunks, sample_response, valid_verdict_json, monkeypatch):
        """Test that Authorization header has correct Bearer format."""
        api_key = "test-key-xyz"
        monkeypatch.setenv("DEEPSEEK_API_KEY", api_key)

        captured_requests = []

        def handler(req):
            captured_requests.append(req)
            return make_api_response(valid_verdict_json)

        mock_transport = httpx.MockTransport(handler)

        with httpx.Client(transport=mock_transport) as client:
            judge_case(sample_case, sample_response, sample_chunks, client=client)

        assert len(captured_requests) > 0
        request = captured_requests[0]

        # Check Authorization header
        auth_header = request.headers.get("Authorization")
        assert auth_header == f"Bearer {api_key}"

    def test_response_format_json_object(self, sample_case, sample_chunks, sample_response, valid_verdict_json):
        """Test that response_format is set to json_object."""
        captured_requests = []

        def handler(req):
            captured_requests.append(req)
            return make_api_response(valid_verdict_json)

        mock_transport = httpx.MockTransport(handler)

        with httpx.Client(transport=mock_transport) as client:
            judge_case(sample_case, sample_response, sample_chunks, client=client)

        assert len(captured_requests) > 0
        request = captured_requests[0]
        body = request.content.decode() if isinstance(request.content, bytes) else request.content

        assert '"type":"json_object"' in body

    def test_temperature_zero(self, sample_case, sample_chunks, sample_response, valid_verdict_json):
        """Test that temperature is set to 0."""
        captured_requests = []

        def handler(req):
            captured_requests.append(req)
            return make_api_response(valid_verdict_json)

        mock_transport = httpx.MockTransport(handler)

        with httpx.Client(transport=mock_transport) as client:
            judge_case(sample_case, sample_response, sample_chunks, client=client)

        assert len(captured_requests) > 0
        request = captured_requests[0]
        body = request.content.decode() if isinstance(request.content, bytes) else request.content

        # Check temperature is 0
        assert '"temperature":0' in body

    def test_timeout_60_seconds(self, sample_case, sample_chunks, sample_response, valid_verdict_json, monkeypatch):
        """Test that client timeout is set to 60 seconds when creating temporary client."""
        timeout_values = []

        def handler(req):
            return make_api_response(valid_verdict_json)

        mock_transport = httpx.MockTransport(handler)

        original_client = httpx.Client

        class MockClient:
            def __init__(self, **kwargs):
                timeout_values.append(kwargs.get("timeout"))
                self._client = original_client(transport=mock_transport, **kwargs)

            def __enter__(self):
                return self._client.__enter__()

            def __exit__(self, *args):
                return self._client.__exit__(*args)

            def post(self, url, **kwargs):
                return self._client.post(url, **kwargs)

        monkeypatch.setattr("httpx.Client", MockClient)

        judge_case(sample_case, sample_response, sample_chunks, client=None)

        assert 60 in timeout_values
