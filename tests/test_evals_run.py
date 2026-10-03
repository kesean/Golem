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
from evals.models import EvalRunPayload, CaseResult, RunSummary, RulePassRate


@pytest.fixture
def two_cases_file():
    """Path to the two-case fixture."""
    return Path(__file__).parent.parent / "evals" / "fixtures" / "two_cases.json"


@pytest.fixture
def offline_env(monkeypatch):
    """Set EVAL_FAKE_PIPELINE=1 for deterministic stub answers. Clear Convex env vars to prevent real network calls."""
    monkeypatch.setenv("EVAL_FAKE_PIPELINE", "1")
    monkeypatch.delenv("CONVEX_SITE_URL", raising=False)
    monkeypatch.delenv("EVAL_INGEST_SECRET", raising=False)


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
        assert "# Eval Run Report" in report_text
        assert "## Summary" in report_text
        assert "Mean Score" in report_text

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
        """When --no-upload is not set, upload is called with Bearer token and camelCase payload."""
        from evals.run import main

        # Mock response for POST /evals/runs
        mock_post_response = Mock()
        mock_post_response.json.return_value = {"runId": "fake-run-id-123"}
        mock_post_response.status_code = 200

        # Mock response for GET /evals/baseline (no baseline)
        mock_get_response = Mock()
        mock_get_response.json.return_value = None
        mock_get_response.status_code = 200

        env = {
            "EVAL_FAKE_PIPELINE": "1",
            "CONVEX_SITE_URL": "https://fake.convex.cloud",
            "EVAL_INGEST_SECRET": "fake-secret-key",
        }

        with patch.dict(os.environ, env, clear=False):
            with patch("httpx.Client.get", return_value=mock_get_response) as mock_get:
                with patch("httpx.Client.post", return_value=mock_post_response) as mock_post:
                    exit_code = main(
                        label="manual",
                        cases_file=str(two_cases_file),
                        out_dir=str(tmp_path),
                        no_upload=False,
                        dry_judge=True,
                        concurrency=1,
                    )

                    # Verify upload (POST) was called
                    assert mock_post.called
                    post_call_args = mock_post.call_args

                    # Check POST URL ends with /evals/runs
                    post_url = post_call_args[0][0]
                    assert post_url.endswith("/evals/runs")

                    # Check bearer token
                    headers = post_call_args.kwargs.get("headers") or {}
                    assert "Authorization" in headers
                    assert headers["Authorization"] == "Bearer fake-secret-key"

                    # Check payload is camelCase
                    payload_dict = post_call_args.kwargs.get("json", {})
                    assert "rulePassRate" in payload_dict["run"]["summary"]
                    assert "gitSha" in payload_dict["run"]

        assert exit_code == 0
        # run.json should have runId added after upload
        run_file = tmp_path / "run.json"
        with open(run_file) as f:
            payload = json.load(f)
        assert payload["run"].get("runId") == "fake-run-id-123"

    def test_no_upload_flag_skips_upload(self, two_cases_file, offline_env, tmp_path):
        """When --no-upload is passed, upload is not called."""
        from evals.run import main

        env = {
            "EVAL_FAKE_PIPELINE": "1",
        }

        with patch.dict(os.environ, env, clear=False):
            with patch("evals.run.convex_client.upload") as mock_upload:
                exit_code = main(
                    label="manual",
                    cases_file=str(two_cases_file),
                    out_dir=str(tmp_path),
                    no_upload=True,
                    dry_judge=True,
                    concurrency=1,
                )

                # Should not be called
                assert not mock_upload.called

        assert exit_code == 0

    def test_upload_failure_exits_1(self, two_cases_file, offline_env, tmp_path):
        """When upload is requested but fails, exit code is 1."""
        from evals.run import main

        env = {
            "EVAL_FAKE_PIPELINE": "1",
            "CONVEX_SITE_URL": "https://fake.convex.cloud",
            "EVAL_INGEST_SECRET": "fake-secret",
        }

        with patch.dict(os.environ, env, clear=False):
            with patch("evals.run.convex_client.upload", return_value=None):
                exit_code = main(
                    label="manual",
                    cases_file=str(two_cases_file),
                    out_dir=str(tmp_path),
                    no_upload=False,
                    dry_judge=True,
                    concurrency=1,
                )

        # Should exit with 1 (harness error) due to upload failure
        assert exit_code == 1


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
            rule_pass_rate=RulePassRate(
                completed=1.0,
                format=1.0,
                product_tag=1.0,
                citations=1.0,
                retrieval=1.0,
            ),
            p50_latency_ms=1000.0,
            p95_latency_ms=1000.0,
            total_input_tokens=100,
            total_output_tokens=50,
        )

        with patch.dict(os.environ, env, clear=False):
            with patch(
                "evals.run.convex_client.fetch_baseline",
                return_value=(fake_baseline_summary, fake_baseline_results, 5.0, "fake-baseline-run-id"),
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

    def test_exit_1_ungraded_skips_regressions(self, two_cases_file, offline_env, tmp_path):
        """When graded_count == 0, skip regression detection (regressions should be empty)."""
        from evals.run import main
        from unittest.mock import patch

        env = {
            "EVAL_FAKE_PIPELINE": "1",
            "CONVEX_SITE_URL": "https://fake.convex.cloud",
            "EVAL_INGEST_SECRET": "fake-secret",
        }

        # Mock judge_case to always fail
        def mock_judge_case(*args, **kwargs):
            return None, "simulated_error"

        # Mock fetch_baseline to return a high-score baseline (would normally cause regression)
        fake_baseline_summary = RunSummary(
            case_count=1,
            graded_count=1,
            error_count=0,
            mean_groundedness=5.0,
            mean_coverage=5.0,
            mean_score=5.0,
            rule_pass_rate=RulePassRate(
                completed=1.0,
                format=1.0,
                product_tag=1.0,
                citations=1.0,
                retrieval=1.0,
            ),
            p50_latency_ms=1000.0,
            p95_latency_ms=1000.0,
            total_input_tokens=100,
            total_output_tokens=50,
        )

        fake_baseline_results = [
            CaseResult(
                case_id="clerk-auth-sessions-test-001",
                question="How do I create a session?",
                response="stub",
                product_tag="Authentication",
                retrieved_urls=["https://clerk.com"],
                rules={"completed": True, "format": True, "product_tag": True, "citations": True, "retrieval": True},
                judge={"groundedness": 5, "coverage": 5, "key_points_missed": [], "reason": "Perfect."},
                latency_ms=1000,
                input_tokens=100,
                output_tokens=50,
            )
        ]

        with patch.dict(os.environ, env, clear=False):
            with patch("evals.run.judge_case", side_effect=mock_judge_case):
                with patch(
                    "evals.run.convex_client.fetch_baseline",
                    return_value=(fake_baseline_summary, fake_baseline_results, 5.0, "fake-baseline-id"),
                ):
                    exit_code = main(
                        label="manual",
                        cases_file=str(two_cases_file),
                        out_dir=str(tmp_path),
                        no_upload=True,
                        dry_judge=False,
                        concurrency=1,
                    )

        # Should exit with 1 (ungraded, not 2 from regressions)
        assert exit_code == 1

        # Check that regressions list is empty (regression detection skipped)
        run_file = tmp_path / "run.json"
        with open(run_file) as f:
            payload = json.load(f)
        assert payload["run"]["status"] == "errored"
        assert payload["run"]["regressions"] == []


class TestBaselineRunId:
    """Baseline run ID extraction and setting."""

    def test_baseline_run_id_in_payload(self, two_cases_file, offline_env, tmp_path, monkeypatch):
        """Baseline run _id is extracted and set as baselineRunId in run.json."""
        from evals.run import main

        # Clear env vars to prevent real network calls
        monkeypatch.delenv("CONVEX_SITE_URL", raising=False)
        monkeypatch.delenv("EVAL_INGEST_SECRET", raising=False)

        env = {
            "EVAL_FAKE_PIPELINE": "1",
            "CONVEX_SITE_URL": "https://fake.convex.cloud",
            "EVAL_INGEST_SECRET": "fake-secret",
        }

        fake_baseline_summary = RunSummary(
            case_count=1,
            graded_count=1,
            error_count=0,
            mean_groundedness=4.0,
            mean_coverage=4.0,
            mean_score=4.0,
            rule_pass_rate=RulePassRate(
                completed=1.0, format=1.0, product_tag=1.0, citations=1.0, retrieval=1.0
            ),
            p50_latency_ms=1000.0,
            p95_latency_ms=1000.0,
            total_input_tokens=100,
            total_output_tokens=50,
        )

        fake_baseline_results = [
            CaseResult(
                case_id="test-case",
                question="Test",
                response="test",
                product_tag="Other",
                retrieved_urls=[],
                rules={
                    "completed": True,
                    "format": True,
                    "product_tag": True,
                    "citations": True,
                    "retrieval": True,
                },
                judge={"groundedness": 4, "coverage": 4, "key_points_missed": [], "reason": "OK"},
                latency_ms=1000,
                input_tokens=100,
                output_tokens=50,
            )
        ]

        with patch.dict(os.environ, env, clear=False):
            with patch(
                "evals.run.convex_client.fetch_baseline",
                return_value=(
                    fake_baseline_summary,
                    fake_baseline_results,
                    4.0,
                    "fake-baseline-run-id",
                ),
            ):
                # Also patch fetch_baseline in convex_client to avoid regressions
                # We're only testing baselineRunId extraction, not regression detection
                exit_code = main(
                    label="manual",
                    cases_file=str(two_cases_file),
                    out_dir=str(tmp_path),
                    no_upload=True,
                    dry_judge=True,
                    concurrency=1,
                )

        # With a baseline having score 4 and current run having score 3, exit 2 is expected (regression)
        # But we're testing that baselineRunId is set regardless, so we check the run.json
        assert exit_code in [0, 2]  # Either clean or with regressions is OK for this test

        # Check run.json has baselineRunId
        run_file = tmp_path / "run.json"
        with open(run_file) as f:
            payload = json.load(f)
        assert payload["run"]["baselineRunId"] == "fake-baseline-run-id"


class TestReportRulePassRates:
    """Report generation with distinct rule pass rates."""

    def test_report_distinct_rule_pass_rates(self, offline_env, tmp_path):
        """Report correctly renders all five rule pass rates with distinct values."""
        from evals import report
        from evals.models import Run, JudgeVerdict

        summary = RunSummary(
            case_count=10,
            graded_count=10,
            error_count=0,
            mean_groundedness=3.0,
            mean_coverage=3.0,
            mean_score=3.0,
            rule_pass_rate=RulePassRate(
                completed=1.0,
                format=0.9,
                product_tag=0.8,
                citations=0.7,
                retrieval=0.6,
            ),
            p50_latency_ms=1000.0,
            p95_latency_ms=1200.0,
            total_input_tokens=1000,
            total_output_tokens=500,
        )

        run = Run(
            label="manual",
            git_sha="abc123",
            git_ref="main",
            app_model="claude-sonnet-5",
            judge_model="deepseek-flash",
            cases_version=1,
            started_at=1000000,
            finished_at=1000100,
            status="completed",
            summary=summary,
            regressions=[],
            baseline_run_id=None,
        )

        results = [
            CaseResult(
                case_id="test-1",
                question="Test",
                response="test",
                product_tag="Other",
                retrieved_urls=[],
                rules={
                    "completed": True,
                    "format": True,
                    "product_tag": True,
                    "citations": True,
                    "retrieval": True,
                },
                judge={"groundedness": 3, "coverage": 3, "key_points_missed": [], "reason": "OK"},
                latency_ms=1000,
                input_tokens=100,
                output_tokens=50,
            )
        ]

        report_text = report.generate_report(run, results)

        # Assert all five rule pass rates are rendered with correct values
        assert "**completed**: 100.0%" in report_text
        assert "**format**: 90.0%" in report_text
        assert "**product_tag**: 80.0%" in report_text
        assert "**citations**: 70.0%" in report_text
        assert "**retrieval**: 60.0%" in report_text


class TestWorst5Ordering:
    """Worst 5 cases sorted by ascending score."""

    def test_worst_5_ordering_ascending(self, offline_env, tmp_path):
        """With 6+ graded cases, worst-5 section lists exactly 5 lowest scores in ascending order."""
        from evals import report
        from evals.models import Run

        summary = RunSummary(
            case_count=6,
            graded_count=6,
            error_count=0,
            mean_groundedness=3.0,
            mean_coverage=3.0,
            mean_score=3.0,
            rule_pass_rate=RulePassRate(
                completed=1.0, format=1.0, product_tag=1.0, citations=1.0, retrieval=1.0
            ),
            p50_latency_ms=1000.0,
            p95_latency_ms=1000.0,
            total_input_tokens=600,
            total_output_tokens=300,
        )

        run = Run(
            label="manual",
            git_sha="abc123",
            git_ref="main",
            app_model="claude-sonnet-5",
            judge_model="deepseek-flash",
            cases_version=1,
            started_at=1000000,
            finished_at=1000100,
            status="completed",
            summary=summary,
            regressions=[],
            baseline_run_id=None,
        )

        # Create 6 cases with distinct scores: 5, 4, 3, 2, 1, and one more at 2 to make 6
        results = []
        for i, score in enumerate([5, 4, 3, 2, 1, 2]):
            results.append(
                CaseResult(
                    case_id=f"case-{i}",
                    question=f"Question {i}",
                    response=f"Response {i}",
                    product_tag="Other",
                    retrieved_urls=[],
                    rules={
                        "completed": True,
                        "format": True,
                        "product_tag": True,
                        "citations": True,
                        "retrieval": True,
                    },
                    judge={
                        "groundedness": score,
                        "coverage": score,
                        "key_points_missed": [],
                        "reason": f"Score {score}",
                    },
                    latency_ms=1000,
                    input_tokens=100,
                    output_tokens=50,
                )
            )

        report_text = report.generate_report(run, results)

        # Assert worst 5 section exists
        assert "## Worst 5 Cases" in report_text

        # Extract the case IDs from the report in the order they appear
        lines = report_text.split("\n")
        worst_cases = []
        for line in lines:
            if "### " in line and ("case-" in line):
                # Extract case ID from line like "### 1. case-5"
                case_id = line.split("case-")[1].split("\n")[0].strip()
                worst_cases.append(int(case_id))

        # Should have exactly 5 cases (worst 5)
        assert len(worst_cases) == 5

        # Verify they are the 5 lowest scores in ascending score order
        # Cases are [5, 4, 3, 2, 1, 2] at indices [0, 1, 2, 3, 4, 5]
        # Sorted by score: score 1 (idx 4), score 2 (idx 3), score 2 (idx 5), score 3 (idx 2), score 4 (idx 1), score 5 (idx 0)
        # Worst 5 (lowest 5) in ascending score order: [4, 3, 5, 2, 1]
        assert worst_cases == [4, 3, 5, 2, 1]
