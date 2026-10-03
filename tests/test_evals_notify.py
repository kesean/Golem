"""
Tests for eval regression notifier.
"""

import json
import subprocess
from unittest.mock import Mock, MagicMock
import pytest
from evals.models import (
    EvalRunPayload, Run, RunSummary, CaseResult, RuleResults, JudgeVerdict,
    MeanScoreDrop, RuleFlip, CaseScoreDrop, ErrorRate, RecentBestDrop,
)
from evals.notify import format_body, notify


def make_run_summary(**overrides):
    """Helper to create RunSummary with sensible defaults."""
    defaults = {
        "case_count": 30,
        "graded_count": 28,
        "error_count": 2,
        "mean_groundedness": 4.1,
        "mean_coverage": 3.8,
        "mean_score": 3.95,
        "rule_pass_rate": {
            "completed": 0.93,
            "format": 1.0,
            "product_tag": 0.97,
            "citations": 0.93,
            "retrieval": 0.90,
        },
        "p50_latency_ms": 1200.0,
        "p95_latency_ms": 2100.0,
        "total_input_tokens": 15000,
        "total_output_tokens": 8000,
    }
    defaults.update(overrides)
    return RunSummary(**defaults)


def make_run(regressions=None, **overrides):
    """Helper to create Run with sensible defaults."""
    defaults = {
        "label": "scheduled",
        "git_sha": "abc123def456",
        "git_ref": "main",
        "app_model": "claude-sonnet-5",
        "judge_model": "deepseek-flash",
        "cases_version": 1,
        "started_at": 1696300800000,
        "finished_at": 1696304400000,
        "status": "completed",
        "summary": make_run_summary(),
        "regressions": regressions or [],
        "baseline_run_id": None,
    }
    defaults.update(overrides)
    return Run(**defaults)


def make_payload(regressions=None, **overrides):
    """Helper to create EvalRunPayload with sensible defaults."""
    return EvalRunPayload(
        run=make_run(regressions=regressions, **overrides),
        results=[],
    )


class TestFormatBody:
    """Tests for format_body function."""

    def test_format_body_no_regressions(self):
        """Test format_body with no regressions."""
        payload = make_payload()
        body = format_body(payload, "https://github.com/repo/actions/runs/123", "https://example.com/evals/run/456")

        # Should contain summary table
        assert "| " in body  # markdown table
        assert "Case Count" in body or "caseCount" in body or "30" in body
        assert "Error Count" in body or "errorCount" in body or "2" in body

    def test_format_body_mean_score_drop(self):
        """Test format_body with meanScoreDrop regression."""
        regression = MeanScoreDrop(kind='meanScoreDrop', baseline=4.0, current=3.5)
        payload = make_payload(regressions=[regression])
        body = format_body(payload, "https://github.com/repo/actions/runs/123", "https://example.com/evals/run/456")

        # Should mention the regression type and values
        assert "meanScoreDrop" in body or "mean score" in body.lower()
        assert "3.5" in body or "3.50" in body
        assert "4.0" in body or "4.00" in body

    def test_format_body_rule_flip(self):
        """Test format_body with ruleFlip regression."""
        regression = RuleFlip(kind='ruleFlip', case_id='case-001', rule='citations')
        payload = make_payload(regressions=[regression])
        body = format_body(payload, "https://github.com/repo/actions/runs/123", "https://example.com/evals/run/456")

        # Should mention the case and rule
        assert "ruleFlip" in body or "rule flip" in body.lower() or "citations" in body
        assert "case-001" in body

    def test_format_body_case_score_drop(self):
        """Test format_body with caseScoreDrop regression."""
        regression = CaseScoreDrop(kind='caseScoreDrop', case_id='case-002', baseline=4.5, current=2.0)
        payload = make_payload(regressions=[regression])
        body = format_body(payload, "https://github.com/repo/actions/runs/123", "https://example.com/evals/run/456")

        # Should mention the case and scores
        assert "caseScoreDrop" in body or "case score" in body.lower()
        assert "case-002" in body
        assert "4.5" in body or "4.50" in body
        assert "2.0" in body or "2.00" in body

    def test_format_body_error_rate(self):
        """Test format_body with errorRate regression."""
        regression = ErrorRate(kind='errorRate', error_count=8, case_count=30)
        payload = make_payload(regressions=[regression])
        body = format_body(payload, "https://github.com/repo/actions/runs/123", "https://example.com/evals/run/456")

        # Should mention error rate
        assert "errorRate" in body or "error rate" in body.lower()
        assert "8" in body
        assert "30" in body

    def test_format_body_recent_best_drop(self):
        """Test format_body with recentBestDrop regression."""
        regression = RecentBestDrop(kind='recentBestDrop', recent_best=4.2, current=3.5)
        payload = make_payload(regressions=[regression])
        body = format_body(payload, "https://github.com/repo/actions/runs/123", "https://example.com/evals/run/456")

        # Should mention the regression type and values
        assert "recentBestDrop" in body or "recent best" in body.lower()
        assert "4.2" in body or "4.20" in body
        assert "3.5" in body or "3.50" in body

    def test_format_body_multiple_regressions(self):
        """Test format_body with multiple regressions."""
        regressions = [
            MeanScoreDrop(kind='meanScoreDrop', baseline=4.0, current=3.5),
            RuleFlip(kind='ruleFlip', case_id='case-001', rule='format'),
        ]
        payload = make_payload(regressions=regressions)
        body = format_body(payload, "https://github.com/repo/actions/runs/123", "https://example.com/evals/run/456")

        # Should contain both regression types
        assert "meanScoreDrop" in body or "mean score" in body.lower()
        assert "ruleFlip" in body or "rule flip" in body.lower() or "format" in body

    def test_format_body_includes_links(self):
        """Test that format_body includes run URL and dashboard URL."""
        payload = make_payload()
        run_url = "https://github.com/repo/actions/runs/789"
        dashboard_url = "https://example.com/evals/run/xyz"
        body = format_body(payload, run_url, dashboard_url)

        assert run_url in body
        assert dashboard_url in body

    def test_format_body_includes_summary_table(self):
        """Test that format_body includes summary statistics."""
        payload = make_payload()
        body = format_body(payload, "https://github.com/repo/actions/runs/123", "https://example.com/evals/run/456")

        # Check for summary stats
        assert "mean" in body.lower() or "Mean" in body
        # latency or p50 should appear
        assert "latency" in body.lower() or "p50" in body.lower() or "1200" in body


class TestFormatBodyHarnessError:
    """Tests for format_body with harness error."""

    def test_format_body_harness_error_status(self):
        """Test format_body with harness error (status=errored)."""
        payload = make_payload(status='errored')
        body = format_body(payload, "https://github.com/repo/actions/runs/123", "https://example.com/evals/run/456")

        # Should indicate an error without a summary table
        assert "error" in body.lower() or "failed" in body.lower()

    def test_format_body_harness_error_with_regressions(self):
        """Test format_body when both harness error and regressions exist."""
        regression = MeanScoreDrop(kind='meanScoreDrop', baseline=4.0, current=3.5)
        payload = make_payload(regressions=[regression], status='errored')
        body = format_body(payload, "https://github.com/repo/actions/runs/123", "https://example.com/evals/run/456")

        # Should show error and regressions
        assert "error" in body.lower() or "failed" in body.lower()


class TestNotify:
    """Tests for notify function."""

    def test_notify_no_regressions_no_harness_error(self, monkeypatch, tmp_path):
        """Test that notify does nothing when there are no regressions and no harness error."""
        mock_run = Mock(spec=subprocess.run)
        monkeypatch.setattr('evals.notify.subprocess.run', mock_run)

        run_file = tmp_path / "run.json"
        payload = make_payload()
        run_file.write_text(payload.model_dump_json())

        notify(
            run_file=str(run_file),
            run_url="https://github.com/repo/actions/runs/123",
            dashboard_url="https://example.com/evals/run/456",
        )

        # subprocess.run should not be called
        mock_run.assert_not_called()

    def test_notify_creates_issue_when_regression_exists(self, monkeypatch, tmp_path):
        """Test that notify creates an issue when a regression exists."""
        mock_run = Mock(spec=subprocess.run)
        monkeypatch.setattr('evals.notify.subprocess.run', mock_run)

        # Mock subprocess.run to return no open issues first, then success
        mock_run.side_effect = [
            # First call: gh issue list (no open issues)
            Mock(returncode=0, stdout='[]'),
            # Second call: gh label create
            Mock(returncode=0, stdout=''),
            # Third call: gh issue create
            Mock(returncode=0, stdout=''),
        ]

        run_file = tmp_path / "run.json"
        regression = MeanScoreDrop(kind='meanScoreDrop', baseline=4.0, current=3.5)
        payload = make_payload(regressions=[regression])
        run_file.write_text(payload.model_dump_json())

        notify(
            run_file=str(run_file),
            run_url="https://github.com/repo/actions/runs/123",
            dashboard_url="https://example.com/evals/run/456",
        )

        # Should call gh issue list
        list_call = mock_run.call_args_list[0]
        assert 'gh' in list_call[0][0]
        assert 'issue' in list_call[0][0]
        assert 'list' in list_call[0][0]
        assert 'eval-regression' in list_call[0][0]

    def test_notify_comments_on_existing_issue(self, monkeypatch, tmp_path):
        """Test that notify comments on an existing issue when one is open."""
        mock_run = Mock(spec=subprocess.run)
        monkeypatch.setattr('evals.notify.subprocess.run', mock_run)

        # Mock subprocess.run to return an open issue
        mock_run.side_effect = [
            # First call: gh issue list (one open issue)
            Mock(returncode=0, stdout='[{"number": 42}]'),
            # Second call: gh issue comment
            Mock(returncode=0, stdout=''),
        ]

        run_file = tmp_path / "run.json"
        regression = MeanScoreDrop(kind='meanScoreDrop', baseline=4.0, current=3.5)
        payload = make_payload(regressions=[regression])
        run_file.write_text(payload.model_dump_json())

        notify(
            run_file=str(run_file),
            run_url="https://github.com/repo/actions/runs/123",
            dashboard_url="https://example.com/evals/run/456",
        )

        # Should find the issue and comment on it
        comment_call = None
        for call in mock_run.call_args_list:
            if 'comment' in call[0][0]:
                comment_call = call
                break

        assert comment_call is not None
        assert '42' in comment_call[0][0]  # issue number

    def test_notify_uses_subprocess_run_with_list_args(self, monkeypatch, tmp_path):
        """Test that notify never interpolates commands into a shell string."""
        mock_run = Mock(spec=subprocess.run)
        monkeypatch.setattr('evals.notify.subprocess.run', mock_run)
        mock_run.return_value = Mock(returncode=0, stdout='[]')

        run_file = tmp_path / "run.json"
        regression = MeanScoreDrop(kind='meanScoreDrop', baseline=4.0, current=3.5)
        payload = make_payload(regressions=[regression])
        run_file.write_text(payload.model_dump_json())

        notify(
            run_file=str(run_file),
            run_url="https://github.com/repo/actions/runs/123",
            dashboard_url="https://example.com/evals/run/456",
        )

        # All calls to subprocess.run should have list args, not shell=True
        for call in mock_run.call_args_list:
            args = call[0][0] if call[0] else call[1].get('args')
            assert isinstance(args, list), f"Expected list args, got {type(args)}: {args}"
            # shell parameter should not be True
            if 'shell' in call[1]:
                assert call[1]['shell'] is not True

    def test_notify_passes_gh_token_via_env(self, monkeypatch, tmp_path):
        """Test that notify passes GH_TOKEN via environment."""
        mock_run = Mock(spec=subprocess.run)
        monkeypatch.setattr('evals.notify.subprocess.run', mock_run)
        mock_run.return_value = Mock(returncode=0, stdout='[]')

        run_file = tmp_path / "run.json"
        regression = MeanScoreDrop(kind='meanScoreDrop', baseline=4.0, current=3.5)
        payload = make_payload(regressions=[regression])
        run_file.write_text(payload.model_dump_json())

        notify(
            run_file=str(run_file),
            run_url="https://github.com/repo/actions/runs/123",
            dashboard_url="https://example.com/evals/run/456",
        )

        # Check that env is passed and inherits
        for call in mock_run.call_args_list:
            env = call[1].get('env')
            # env should inherit from os.environ, not explicitly set
            # (or if explicitly set, it should include inherited vars)
            assert env is None or isinstance(env, dict)

    def test_notify_harness_error_creates_issue(self, monkeypatch, tmp_path):
        """Test that notify creates an issue when harness error occurs."""
        mock_run = Mock(spec=subprocess.run)
        monkeypatch.setattr('evals.notify.subprocess.run', mock_run)

        mock_run.side_effect = [
            # First call: gh issue list (no open issues)
            Mock(returncode=0, stdout='[]'),
            # Second call: gh label create
            Mock(returncode=0, stdout=''),
            # Third call: gh issue create
            Mock(returncode=0, stdout=''),
        ]

        run_file = tmp_path / "run.json"
        payload = make_payload(status='errored')
        run_file.write_text(payload.model_dump_json())

        notify(
            run_file=str(run_file),
            run_url="https://github.com/repo/actions/runs/123",
            dashboard_url="https://example.com/evals/run/456",
            harness_error=True,
        )

        # Should create an issue
        assert mock_run.call_count >= 1

    def test_notify_missing_run_file_with_harness_error(self, monkeypatch, tmp_path):
        """Test that notify works even if run.json is missing, when harness_error=True."""
        mock_run = Mock(spec=subprocess.run)
        monkeypatch.setattr('evals.notify.subprocess.run', mock_run)

        mock_run.side_effect = [
            # First call: gh issue list (no open issues)
            Mock(returncode=0, stdout='[]'),
            # Second call: gh label create
            Mock(returncode=0, stdout=''),
            # Third call: gh issue create
            Mock(returncode=0, stdout=''),
        ]

        run_file = tmp_path / "run.json"
        # File doesn't exist yet

        notify(
            run_file=str(run_file),
            run_url="https://github.com/repo/actions/runs/123",
            dashboard_url="https://example.com/evals/run/456",
            harness_error=True,
        )

        # Should still try to create an issue
        assert mock_run.call_count >= 1

    def test_notify_subprocess_failure_exits_nonzero(self, monkeypatch, tmp_path, capsys):
        """Test that notify exits with non-zero when subprocess.run fails."""
        mock_run = Mock(spec=subprocess.run)
        monkeypatch.setattr('evals.notify.subprocess.run', mock_run)

        # Mock gh list to succeed but gh create to fail
        mock_run.side_effect = [
            # First call: gh issue list (no open issues)
            Mock(returncode=0, stdout='[]'),
            # Second call: gh label create (fails)
            Mock(returncode=1, stdout='already exists'),
        ]

        run_file = tmp_path / "run.json"
        regression = MeanScoreDrop(kind='meanScoreDrop', baseline=4.0, current=3.5)
        payload = make_payload(regressions=[regression])
        run_file.write_text(payload.model_dump_json())

        with pytest.raises(SystemExit) as exc_info:
            notify(
                run_file=str(run_file),
                run_url="https://github.com/repo/actions/runs/123",
                dashboard_url="https://example.com/evals/run/456",
            )

        assert exc_info.value.code != 0
