"""
Tests for evals.run module — the main CLI orchestrator.

Tests offline runs with EVAL_FAKE_PIPELINE and mocked Convex uploads.
No network calls to real endpoints.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
import httpx
from evals.models import EvalRunPayload, CaseResult, RunSummary


@pytest.fixture
def two_cases_file():
    """Path to the two-case fixture."""
    return Path(__file__).parent.parent / "evals" / "fixtures" / "two_cases.json"


@pytest.fixture
def offline_env():
    """Set EVAL_FAKE_PIPELINE=1 for deterministic stub answers."""
    with patch.dict(os.environ, {"EVAL_FAKE_PIPELINE": "1"}):
        yield


class TestOfflineRun:
    """Offline run with EVAL_FAKE_PIPELINE=1 and --dry-judge."""

    def test_offline_run_with_no_upload(self, two_cases_file, offline_env, tmp_path):
        """Run offline with --no-upload and --dry-judge, exits 0."""
        from evals.run import main

        # Set environment for offline mode
        env = {
            "EVAL_FAKE_PIPELINE": "1",
        }

        with patch.dict(os.environ, env, clear=False):
            # Run with --no-upload and --dry-judge
            exit_code = main(
                label="manual",
                cases_file=str(two_cases_file),
                out_dir=str(tmp_path),
                no_upload=True,
                dry_judge=True,
                concurrency=3,
            )

        # Should exit cleanly (no regressions, no baseline)
        assert exit_code == 0

        # Should write run.json
        run_file = tmp_path / "run.json"
        assert run_file.exists()
        with open(run_file) as f:
            payload = json.load(f)
        assert "run" in payload
        assert "results" in payload
        assert payload["run"]["label"] == "manual"
        assert payload["run"]["status"] == "completed"
        assert len(payload["results"]) == 2

        # Should write report.md
        report_file = tmp_path / "report.md"
        assert report_file.exists()
        report_text = report_file.read_text()
        assert "Eval Run Report" in report_text or "Summary" in report_text.lower()

    def test_offline_run_writes_files(self, two_cases_file, offline_env, tmp_path):
        """Offline run writes both run.json and report.md."""
        from evals.run import main

        env = {
            "EVAL_FAKE_PIPELINE": "1",
        }

        with patch.dict(os.environ, env, clear=False):
            exit_code = main(
                label="manual",
                cases_file=str(two_cases_file),
                out_dir=str(tmp_path),
                no_upload=True,
                dry_judge=True,
                concurrency=1,
            )

        assert exit_code == 0
        assert (tmp_path / "run.json").exists()
        assert (tmp_path / "report.md").exists()


class TestPipelineException:
    """Exception handling during case execution."""

    def test_case_exception_recorded(self, two_cases_file, tmp_path):
        """When a case raises an exception, it's recorded and run continues."""
        from evals.run import main
        from unittest.mock import patch, MagicMock

        # Create a mock that raises for the first case
        call_count = [0]
        def mock_stream_run(question, history):
            call_count[0] += 1
            if "session" in question.lower():
                # Raise immediately on first case (which asks about "session")
                raise RuntimeError("Simulated pipeline error")
            # For second case, yield a stub response
            yield {"type": "delta", "text": "<product_tag>CORS</product_tag>"}
            yield {
                "type": "done",
                "response": """<product_tag>CORS</product_tag>
<summary>Fix CORS errors by setting headers</summary>
<root_cause>Missing CORS headers</root_cause>
<debug_steps>Check headers</debug_steps>
<docs>https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS</docs>""",
                "input_tokens": 100,
                "output_tokens": 50,
                "latency_ms": 1000,
                "chunks": [{"source": "mdn", "url": "https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS"}],
            }

        # Do NOT set EVAL_FAKE_PIPELINE so our mock is called
        with patch("evals.run.chat.stream_run", side_effect=mock_stream_run):
            exit_code = main(
                label="manual",
                cases_file=str(two_cases_file),
                out_dir=str(tmp_path),
                no_upload=True,
                dry_judge=True,
                concurrency=1,
            )

        assert exit_code == 0  # Run completes despite exception

        # Check that error was recorded
        run_file = tmp_path / "run.json"
        with open(run_file) as f:
            payload = json.load(f)

        results = payload["results"]
        assert len(results) == 2

        # First case should have error (field present and non-empty)
        # The error message should contain "Simulated" or just check that error exists
        assert "error" in results[0], f"Error field missing from first result: {results[0]}"
        assert results[0]["error"] is not None
        assert "Simulated" in results[0]["error"] or "pipeline" in results[0]["error"].lower()
        assert results[0]["response"] == ""

        # Second case should not have error field (excluded by exclude_none)
        assert "error" not in results[1], f"Error field should not be in second result: {results[1]}"


class TestUploadCall:
    """Verify upload behavior."""

    def test_upload_called_with_bearer_token(self, two_cases_file, offline_env, tmp_path):
        """When --no-upload is not set, upload is called with Bearer token."""
        from evals.run import main

        mock_response = Mock()
        mock_response.json.return_value = {"runId": "fake-run-id-123"}
        mock_response.status_code = 200

        env = {
            "EVAL_FAKE_PIPELINE": "1",
            "CONVEX_SITE_URL": "https://fake.convex.cloud",
            "EVAL_INGEST_SECRET": "fake-secret-key",
        }

        with patch.dict(os.environ, env, clear=False):
            with patch("httpx.Client.post", return_value=mock_response) as mock_post:
                exit_code = main(
                    label="manual",
                    cases_file=str(two_cases_file),
                    out_dir=str(tmp_path),
                    no_upload=False,
                    dry_judge=True,
                    concurrency=1,
                )

                # Verify upload was called
                assert mock_post.called
                call_args = mock_post.call_args

                # Check bearer token
                headers = call_args.kwargs.get("headers") or {}
                assert "Authorization" in headers
                assert headers["Authorization"] == "Bearer fake-secret-key"

        assert exit_code == 0
        # run.json should have runId added after upload
        run_file = tmp_path / "run.json"
        with open(run_file) as f:
            payload = json.load(f)
        assert payload["run"].get("runId") == "fake-run-id-123"

    def test_no_upload_flag_skips_upload(self, two_cases_file, offline_env, tmp_path):
        """When --no-upload is passed, upload is not called."""
        from evals.run import main

        mock_post = Mock()

        env = {
            "EVAL_FAKE_PIPELINE": "1",
        }

        with patch.dict(os.environ, env, clear=False):
            with patch("httpx.Client.post", mock_post) as patched:
                exit_code = main(
                    label="manual",
                    cases_file=str(two_cases_file),
                    out_dir=str(tmp_path),
                    no_upload=True,
                    dry_judge=True,
                    concurrency=1,
                )

                # Should not be called
                assert not patched.called

        assert exit_code == 0


class TestRegressionDetection:
    """Exit code 2 when regressions are detected."""

    def test_exit_2_on_regression(self, two_cases_file, offline_env, tmp_path):
        """Exit code 2 when find_regressions returns regressions."""
        from evals.run import main
        from unittest.mock import patch

        env = {
            "EVAL_FAKE_PIPELINE": "1",
            "CONVEX_SITE_URL": "https://fake.convex.cloud",
            "EVAL_INGEST_SECRET": "fake-secret",
        }

        # Mock convex_client.fetch_baseline to return a baseline with high score
        fake_baseline_results = [
            CaseResult(
                case_id="clerk-auth-sessions-test-001",
                question="How do I create a session?",
                response="stub",
                product_tag="Authentication",
                retrieved_urls=["https://clerk.com"],
                rules={
                    "completed": True,
                    "format": True,
                    "product_tag": True,
                    "citations": True,
                    "retrieval": True,
                },
                judge={
                    "groundedness": 5,
                    "coverage": 5,
                    "key_points_missed": [],
                    "reason": "Perfect.",
                },
                latency_ms=1000,
                input_tokens=100,
                output_tokens=50,
            )
        ]

        fake_baseline_summary = RunSummary(
            case_count=1,
            graded_count=1,
            error_count=0,
            mean_groundedness=5.0,
            mean_coverage=5.0,
            mean_score=5.0,
            rule_pass_rate={
                "completed": 1.0,
                "format": 1.0,
                "product_tag": 1.0,
                "citations": 1.0,
                "retrieval": 1.0,
            },
            p50_latency_ms=1000.0,
            p95_latency_ms=1000.0,
            total_input_tokens=100,
            total_output_tokens=50,
        )

        with patch.dict(os.environ, env, clear=False):
            with patch(
                "evals.run.convex_client.fetch_baseline",
                return_value=(fake_baseline_summary, fake_baseline_results, 5.0),
            ):
                exit_code = main(
                    label="manual",
                    cases_file=str(two_cases_file),
                    out_dir=str(tmp_path),
                    no_upload=True,
                    dry_judge=True,
                    concurrency=1,
                )

        # Should exit with 2 (regressions) because mean score dropped
        assert exit_code == 2


class TestUngradedRun:
    """When no cases are graded, run status is errored and exit code is 1."""

    def test_exit_1_on_no_graded_cases(self, two_cases_file, offline_env, tmp_path):
        """When graded_count == 0, set status to errored and exit 1."""
        from evals.run import main
        from unittest.mock import patch

        env = {
            "EVAL_FAKE_PIPELINE": "1",
        }

        # Mock judge_case to always fail (return None, "error")
        def mock_judge_case(*args, **kwargs):
            return None, "simulated_error"

        with patch.dict(os.environ, env, clear=False):
            with patch("evals.run.judge_case", side_effect=mock_judge_case):
                exit_code = main(
                    label="manual",
                    cases_file=str(two_cases_file),
                    out_dir=str(tmp_path),
                    no_upload=True,
                    dry_judge=False,  # Will call judge_case which fails
                    concurrency=1,
                )

        # Should exit with 1 (harness error, not regressions)
        assert exit_code == 1

        # Check that status is errored
        run_file = tmp_path / "run.json"
        with open(run_file) as f:
            payload = json.load(f)
        assert payload["run"]["status"] == "errored"
        assert payload["run"]["summary"]["gradedCount"] == 0
