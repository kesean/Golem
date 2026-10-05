"""
Tests for evals.convex_client module.

Tests fetch_baseline and upload with mocked httpx, covering:
- Successful baseline fetch and deserialization from Convex doc format
- Null baseline response
- HTTP errors (401, 404, 5xx)
- Missing environment configuration
- Upload with proper bearer token
"""

import os
from unittest.mock import Mock, patch

import pytest
from evals.models import RulePassRate


@pytest.fixture
def convex_baseline_doc():
    """A Convex baseline response document."""
    return {
        "run": {
            "_id": "baseline-doc-id-12345",
            "_creationTime": 1696262400000,
            "label": "scheduled",
            "gitSha": "abc123def456",
            "gitRef": "main",
            "appModel": "claude-sonnet-5",
            "judgeModel": "deepseek-flash",
            "casesVersion": 1,
            "startedAt": 1696262400000,
            "finishedAt": 1696262430000,
            "status": "completed",
            "summary": {
                "caseCount": 2,
                "gradedCount": 2,
                "errorCount": 0,
                "meanGroundedness": 4.0,
                "meanCoverage": 4.5,
                "meanScore": 4.25,
                "rulePassRate": {
                    "completed": 1.0,
                    "format": 0.95,
                    "productTag": 0.9,
                    "citations": 0.85,
                    "retrieval": 0.8,
                },
                "p50LatencyMs": 1200.0,
                "p95LatencyMs": 1500.0,
                "totalInputTokens": 450,
                "totalOutputTokens": 280,
            },
            "regressions": [],
            "baselineRunId": None,
        },
        "results": [
            {
                "_id": "result-1",
                "runId": "baseline-doc-id-12345",
                "caseId": "case-1",
                "question": "Test question 1",
                "response": "Test response 1",
                "productTag": "Authentication",
                "retrievedUrls": ["https://example.com/1"],
                "rules": {
                    "completed": True,
                    "format": True,
                    "productTag": True,
                    "citations": True,
                    "retrieval": True,
                },
                "judge": {
                    "groundedness": 4,
                    "coverage": 4,
                    "keyPointsMissed": [],
                    "reason": "Good response.",
                },
                "latencyMs": 1000,
                "inputTokens": 200,
                "outputTokens": 120,
            },
            {
                "_id": "result-2",
                "runId": "baseline-doc-id-12345",
                "caseId": "case-2",
                "question": "Test question 2",
                "response": "Test response 2",
                "productTag": "CORS",
                "retrievedUrls": ["https://example.com/2"],
                "rules": {
                    "completed": True,
                    "format": True,
                    "productTag": True,
                    "citations": True,
                    "retrieval": True,
                },
                "judge": {
                    "groundedness": 4,
                    "coverage": 5,
                    "keyPointsMissed": [],
                    "reason": "Excellent coverage.",
                },
                "latencyMs": 1400,
                "inputTokens": 250,
                "outputTokens": 160,
            },
        ],
        "recentBestMeanScore": 4.5,
    }


@pytest.fixture
def convex_baseline_doc_omitted_fields():
    """A Convex baseline response with omitted optional fields (judge, productTag, judgeError)."""
    return {
        "run": {
            "_id": "baseline-doc-id-omitted",
            "_creationTime": 1696262400000,
            "label": "scheduled",
            "gitSha": "abc123",
            "gitRef": "main",
            "appModel": "claude-sonnet-5",
            "judgeModel": "deepseek-flash",
            "casesVersion": 1,
            "startedAt": 1696262400000,
            "finishedAt": 1696262430000,
            "status": "completed",
            "summary": {
                "caseCount": 1,
                "gradedCount": 0,
                "errorCount": 1,
                "meanGroundedness": 0.0,
                "meanCoverage": 0.0,
                "meanScore": 0.0,
                "rulePassRate": {
                    "completed": 0.0,
                    "format": 0.0,
                    "productTag": 0.0,
                    "citations": 0.0,
                    "retrieval": 0.0,
                },
                "p50LatencyMs": 500.0,
                "p95LatencyMs": 500.0,
                "totalInputTokens": 50,
                "totalOutputTokens": 25,
            },
            "regressions": [],
        },
        "results": [
            {
                "_id": "result-omitted",
                "runId": "baseline-doc-id-omitted",
                "caseId": "case-error",
                "question": "Test question",
                "response": "",
                # productTag omitted
                "retrievedUrls": [],
                "rules": {
                    "completed": False,
                    "format": False,
                    "productTag": False,
                    "citations": False,
                    "retrieval": False,
                },
                # judge omitted
                # judgeError omitted
                "latencyMs": 500,
                "inputTokens": 50,
                "outputTokens": 25,
                "error": "Pipeline error",
            }
        ],
        "recentBestMeanScore": 0.0,
    }


class TestFetchBaseline:
    """Tests for fetch_baseline function."""

    def test_fetch_baseline_success(self, convex_baseline_doc):
        """Successfully fetch and deserialize baseline from Convex."""
        from evals.convex_client import fetch_baseline

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = convex_baseline_doc

        env = {
            "CONVEX_SITE_URL": "https://test.convex.cloud",
            "EVAL_INGEST_SECRET": "test-secret",
        }

        with patch.dict(os.environ, env):
            with patch("httpx.Client.get", return_value=mock_response) as mock_get:
                result = fetch_baseline()

        assert result is not None
        summary, results, recent_best, baseline_run_id = result

        # Check summary
        assert summary.case_count == 2
        assert summary.graded_count == 2
        assert summary.error_count == 0
        assert summary.mean_groundedness == 4.0
        assert summary.mean_coverage == 4.5
        assert summary.mean_score == 4.25
        assert recent_best == 4.5
        assert baseline_run_id == "baseline-doc-id-12345"

        # Check rule pass rates
        assert isinstance(summary.rule_pass_rate, RulePassRate)
        assert summary.rule_pass_rate.completed == 1.0
        assert summary.rule_pass_rate.format == 0.95
        assert summary.rule_pass_rate.product_tag == 0.9
        assert summary.rule_pass_rate.citations == 0.85
        assert summary.rule_pass_rate.retrieval == 0.8

        # Check results
        assert len(results) == 2
        assert results[0].case_id == "case-1"
        assert results[0].product_tag == "Authentication"
        assert results[1].case_id == "case-2"
        assert results[1].product_tag == "CORS"

        # Verify GET was called with correct URL and auth
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "evals/baseline" in call_args[0][0]
        headers = call_args.kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer test-secret"

    def test_fetch_baseline_null_response(self):
        """When baseline is null, return None."""
        from evals.convex_client import fetch_baseline

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = None

        env = {
            "CONVEX_SITE_URL": "https://test.convex.cloud",
            "EVAL_INGEST_SECRET": "test-secret",
        }

        with patch.dict(os.environ, env):
            with patch("httpx.Client.get", return_value=mock_response):
                result = fetch_baseline()

        assert result is None

    def test_fetch_baseline_401_unauthorized(self):
        """When 401 Unauthorized, log warning and return None."""
        from evals.convex_client import fetch_baseline

        mock_response = Mock()
        mock_response.status_code = 401

        env = {
            "CONVEX_SITE_URL": "https://test.convex.cloud",
            "EVAL_INGEST_SECRET": "wrong-secret",
        }

        with patch.dict(os.environ, env):
            with patch("httpx.Client.get", return_value=mock_response):
                with patch("evals.convex_client.logger") as mock_logger:
                    result = fetch_baseline()

        assert result is None
        mock_logger.warning.assert_called()
        assert "401" in mock_logger.warning.call_args[0][0]

    def test_fetch_baseline_404_not_found(self):
        """When 404 Not Found, log warning and return None."""
        from evals.convex_client import fetch_baseline

        mock_response = Mock()
        mock_response.status_code = 404

        env = {
            "CONVEX_SITE_URL": "https://test.convex.cloud",
            "EVAL_INGEST_SECRET": "test-secret",
        }

        with patch.dict(os.environ, env):
            with patch("httpx.Client.get", return_value=mock_response):
                with patch("evals.convex_client.logger") as mock_logger:
                    result = fetch_baseline()

        assert result is None
        mock_logger.warning.assert_called()

    def test_fetch_baseline_missing_env(self):
        """When CONVEX_SITE_URL or EVAL_INGEST_SECRET missing, return None."""
        from evals.convex_client import fetch_baseline

        # Clear env vars
        env = {"CONVEX_SITE_URL": "", "EVAL_INGEST_SECRET": ""}

        with patch.dict(os.environ, env, clear=True):
            with patch("evals.convex_client.logger") as mock_logger:
                result = fetch_baseline()

        assert result is None
        mock_logger.warning.assert_called()
        assert "not set" in mock_logger.warning.call_args[0][0]

    def test_fetch_baseline_camel_case_conversion(self):
        """Verify camelCase from Convex is converted to snake_case in models."""
        from evals.convex_client import fetch_baseline

        response_doc = {
            "run": {
                "_id": "test-id",
                "summary": {
                    "caseCount": 5,
                    "gradedCount": 5,
                    "errorCount": 1,
                    "meanGroundedness": 3.5,
                    "meanCoverage": 3.8,
                    "meanScore": 3.65,
                    "rulePassRate": {
                        "completed": 0.8,
                        "format": 0.7,
                        "productTag": 0.6,
                        "citations": 0.9,
                        "retrieval": 0.75,
                    },
                    "p50LatencyMs": 800.0,
                    "p95LatencyMs": 1200.0,
                    "totalInputTokens": 1000,
                    "totalOutputTokens": 500,
                },
                "regressions": [],
            },
            "results": [],
            "recentBestMeanScore": 3.8,
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = response_doc

        env = {
            "CONVEX_SITE_URL": "https://test.convex.cloud",
            "EVAL_INGEST_SECRET": "test-secret",
        }

        with patch.dict(os.environ, env):
            with patch("httpx.Client.get", return_value=mock_response):
                result = fetch_baseline()

        assert result is not None
        summary, results, recent_best, baseline_run_id = result

        # All conversions should work
        assert summary.case_count == 5
        assert summary.mean_groundedness == 3.5
        assert summary.p50_latency_ms == 800.0
        assert summary.total_input_tokens == 1000

    def test_fetch_baseline_omitted_optional_fields(self, convex_baseline_doc_omitted_fields):
        """When judge, productTag, judgeError are omitted from Convex doc, they deserialize to None."""
        from evals.convex_client import fetch_baseline

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = convex_baseline_doc_omitted_fields

        env = {
            "CONVEX_SITE_URL": "https://test.convex.cloud",
            "EVAL_INGEST_SECRET": "test-secret",
        }

        with patch.dict(os.environ, env):
            with patch("httpx.Client.get", return_value=mock_response):
                result = fetch_baseline()

        assert result is not None
        summary, results, recent_best, baseline_run_id = result

        # Check that omitted fields deserialize to None
        assert len(results) == 1
        assert results[0].product_tag is None
        assert results[0].judge is None
        assert results[0].judge_error is None
        assert results[0].error == "Pipeline error"


class TestUpload:
    """Tests for upload function."""

    def test_upload_success(self):
        """Successfully upload eval run payload."""
        from evals.convex_client import upload
        from evals.models import EvalRunPayload, Run, CaseResult, RulePassRate, RunSummary

        # Create a minimal payload
        summary = RunSummary(
            case_count=1,
            graded_count=1,
            error_count=0,
            mean_groundedness=3.0,
            mean_coverage=3.0,
            mean_score=3.0,
            rule_pass_rate=RulePassRate(
                completed=1.0, format=1.0, product_tag=1.0, citations=1.0, retrieval=1.0
            ),
            p50_latency_ms=1000.0,
            p95_latency_ms=1000.0,
            total_input_tokens=100,
            total_output_tokens=50,
        )

        run = Run(
            label="manual",
            git_sha="abc123",
            git_ref="test-branch",
            app_model="claude-sonnet-5",
            judge_model="deepseek-flash",
            cases_version=1,
            started_at=1696262400000,
            finished_at=1696262430000,
            status="completed",
            summary=summary,
            regressions=[],
            baseline_run_id=None,
        )

        results = [
            CaseResult(
                case_id="test-1",
                question="Test question",
                response="Test response",
                product_tag="Authentication",
                retrieved_urls=["https://example.com"],
                rules={
                    "completed": True,
                    "format": True,
                    "product_tag": True,
                    "citations": True,
                    "retrieval": True,
                },
                judge={
                    "groundedness": 3,
                    "coverage": 3,
                    "key_points_missed": [],
                    "reason": "OK response.",
                },
                latency_ms=1000,
                input_tokens=100,
                output_tokens=50,
            )
        ]

        payload = EvalRunPayload(run=run, results=results)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"runId": "uploaded-run-123"}

        env = {
            "CONVEX_SITE_URL": "https://test.convex.cloud",
            "EVAL_INGEST_SECRET": "test-secret",
        }

        with patch.dict(os.environ, env):
            with patch("httpx.Client.post", return_value=mock_response) as mock_post:
                run_id = upload(payload)

        assert run_id == "uploaded-run-123"

        # Verify POST was called with camelCase payload
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "evals/runs" in call_args[0][0]
        headers = call_args.kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer test-secret"

        # Verify payload is in camelCase
        payload_dict = call_args.kwargs.get("json", {})
        assert "run" in payload_dict
        assert payload_dict["run"]["gitSha"] == "abc123"  # camelCase
        assert payload_dict["run"]["startedAt"] == 1696262400000  # camelCase
        assert "rulePassRate" in payload_dict["run"]["summary"]  # camelCase

    def test_upload_failure_returns_none(self):
        """When upload fails (non-200), return None."""
        from evals.convex_client import upload
        from evals.models import EvalRunPayload, Run, CaseResult, RulePassRate, RunSummary

        summary = RunSummary(
            case_count=0,
            graded_count=0,
            error_count=0,
            mean_groundedness=0.0,
            mean_coverage=0.0,
            mean_score=0.0,
            rule_pass_rate=RulePassRate(
                completed=0.0, format=0.0, product_tag=0.0, citations=0.0, retrieval=0.0
            ),
            p50_latency_ms=0.0,
            p95_latency_ms=0.0,
            total_input_tokens=0,
            total_output_tokens=0,
        )

        run = Run(
            label="manual",
            git_sha="abc123",
            git_ref="test",
            app_model="claude-sonnet-5",
            judge_model="deepseek-flash",
            cases_version=1,
            started_at=1696262400000,
            finished_at=1696262430000,
            status="errored",
            summary=summary,
            regressions=[],
            baseline_run_id=None,
        )

        payload = EvalRunPayload(run=run, results=[])

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"

        env = {
            "CONVEX_SITE_URL": "https://test.convex.cloud",
            "EVAL_INGEST_SECRET": "test-secret",
        }

        with patch.dict(os.environ, env):
            with patch("httpx.Client.post", return_value=mock_response):
                with patch("evals.convex_client.logger"):
                    run_id = upload(payload)

        assert run_id is None


class TestTrailingSlashUrl:
    """CONVEX_SITE_URL with a trailing slash must not produce a double slash."""

    def test_fetch_baseline_strips_trailing_slash(self):
        from evals.convex_client import fetch_baseline

        resp = Mock()
        resp.status_code = 200
        resp.json.return_value = None
        env = {"CONVEX_SITE_URL": "https://test.convex.site/", "EVAL_INGEST_SECRET": "s"}
        with patch.dict(os.environ, env):
            with patch("httpx.Client.get", return_value=resp) as mock_get:
                fetch_baseline()
        assert mock_get.call_args[0][0] == "https://test.convex.site/evals/baseline"

    def test_upload_strips_trailing_slash(self):
        from evals.convex_client import upload
        from evals.models import EvalRunPayload

        resp = Mock()
        resp.status_code = 200
        resp.json.return_value = {"runId": "r1"}
        env = {"CONVEX_SITE_URL": "https://test.convex.site//", "EVAL_INGEST_SECRET": "s"}
        payload = Mock(spec=EvalRunPayload)
        payload.model_dump.return_value = {}
        with patch.dict(os.environ, env):
            with patch("httpx.Client.post", return_value=resp) as mock_post:
                assert upload(payload) == "r1"
        assert mock_post.call_args[0][0] == "https://test.convex.site/evals/runs"
