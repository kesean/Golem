"""
Tests for eval regression notifier.
"""

import json
import subprocess
import sys
from unittest.mock import Mock, patch
import pytest
from evals.models import (
    EvalRunPayload, Run, RunSummary, CaseResult, RuleResults, JudgeVerdict,
    MeanScoreDrop, RuleFlip, CaseScoreDrop, ErrorRate, RecentBestDrop,
    RulePassRate,
)
from evals.notify import format_body, notify, main


def make_rule_pass_rate(**overrides):
    """Helper to create RulePassRate with sensible defaults."""
    defaults = {
        "completed": 0.93,
        "format": 1.0,
        "product_tag": 0.97,
        "citations": 0.93,
        "retrieval": 0.90,
    }
    defaults.update(overrides)
    return RulePassRate(**defaults)


def make_run_summary(**overrides):
    """Helper to create RunSummary with sensible defaults."""
    defaults = {
        "case_count": 30,
        "graded_count": 28,
        "error_count": 2,
        "mean_groundedness": 4.1,
        "mean_coverage": 3.8,
        "mean_score": 3.95,
        "rule_pass_rate": make_rule_pass_rate(),
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


class TestFormatBodySnapshots:
    """Snapshot-style tests for format_body output."""

    def test_format_body_no_regressions(self):
        """Test format_body with no regressions — exact string match."""
        payload = make_payload()
        body = format_body(payload, "https://github.com/repo/actions/runs/123", "https://example.com/evals/run/456")

        expected = """\
# Eval Regression Detected

## Summary

| Metric | Value |
|--------|-------|
| Cases | 30 |
| Graded | 28 |
| Errors | 2 |
| Mean Groundedness | 4.10 |
| Mean Coverage | 3.80 |
| Mean Score | 3.95 |
| P50 Latency (ms) | 1200 |
| P95 Latency (ms) | 2100 |
| Total Tokens (in+out) | 23000 |

## Links

- [Workflow Run](https://github.com/repo/actions/runs/123)
- [Evals Dashboard](https://example.com/evals/run/456)

"""
        assert body == expected

    def test_format_body_mean_score_drop(self):
        """Test format_body with meanScoreDrop regression — exact string match."""
        regression = MeanScoreDrop(kind='meanScoreDrop', baseline=4.0, current=3.5)
        payload = make_payload(regressions=[regression])
        body = format_body(payload, "https://github.com/repo/actions/runs/123", "https://example.com/evals/run/456")

        expected = """\
# Eval Regression Detected

## Summary

| Metric | Value |
|--------|-------|
| Cases | 30 |
| Graded | 28 |
| Errors | 2 |
| Mean Groundedness | 4.10 |
| Mean Coverage | 3.80 |
| Mean Score | 3.95 |
| P50 Latency (ms) | 1200 |
| P95 Latency (ms) | 2100 |
| Total Tokens (in+out) | 23000 |

## Regressions

- **Mean Score Drop**: 4.00 → 3.50

## Links

- [Workflow Run](https://github.com/repo/actions/runs/123)
- [Evals Dashboard](https://example.com/evals/run/456)

"""
        assert body == expected

    def test_format_body_rule_flip(self):
        """Test format_body with ruleFlip regression — exact string match."""
        # Note: ruleFlip.rule is now a RuleName (camelCase)
        regression = RuleFlip(kind='ruleFlip', case_id='case-001', rule='productTag')
        payload = make_payload(regressions=[regression])
        body = format_body(payload, "https://github.com/repo/actions/runs/123", "https://example.com/evals/run/456")

        expected = """\
# Eval Regression Detected

## Summary

| Metric | Value |
|--------|-------|
| Cases | 30 |
| Graded | 28 |
| Errors | 2 |
| Mean Groundedness | 4.10 |
| Mean Coverage | 3.80 |
| Mean Score | 3.95 |
| P50 Latency (ms) | 1200 |
| P95 Latency (ms) | 2100 |
| Total Tokens (in+out) | 23000 |

## Regressions

- **Rule Flip** (`productTag`): case `case-001`

## Links

- [Workflow Run](https://github.com/repo/actions/runs/123)
- [Evals Dashboard](https://example.com/evals/run/456)

"""
        assert body == expected

    def test_format_body_case_score_drop(self):
        """Test format_body with caseScoreDrop regression — exact string match."""
        regression = CaseScoreDrop(kind='caseScoreDrop', case_id='case-002', baseline=4.5, current=2.0)
        payload = make_payload(regressions=[regression])
        body = format_body(payload, "https://github.com/repo/actions/runs/123", "https://example.com/evals/run/456")

        expected = """\
# Eval Regression Detected

## Summary

| Metric | Value |
|--------|-------|
| Cases | 30 |
| Graded | 28 |
| Errors | 2 |
| Mean Groundedness | 4.10 |
| Mean Coverage | 3.80 |
| Mean Score | 3.95 |
| P50 Latency (ms) | 1200 |
| P95 Latency (ms) | 2100 |
| Total Tokens (in+out) | 23000 |

## Regressions

- **Case Score Drop**: `case-002` — 4.50 → 2.00

## Links

- [Workflow Run](https://github.com/repo/actions/runs/123)
- [Evals Dashboard](https://example.com/evals/run/456)

"""
        assert body == expected

    def test_format_body_error_rate(self):
        """Test format_body with errorRate regression — exact string match."""
        regression = ErrorRate(kind='errorRate', error_count=8, case_count=30)
        payload = make_payload(regressions=[regression])
        body = format_body(payload, "https://github.com/repo/actions/runs/123", "https://example.com/evals/run/456")

        expected = """\
# Eval Regression Detected

## Summary

| Metric | Value |
|--------|-------|
| Cases | 30 |
| Graded | 28 |
| Errors | 2 |
| Mean Groundedness | 4.10 |
| Mean Coverage | 3.80 |
| Mean Score | 3.95 |
| P50 Latency (ms) | 1200 |
| P95 Latency (ms) | 2100 |
| Total Tokens (in+out) | 23000 |

## Regressions

- **Error Rate**: 8/30 cases (26.7%)

## Links

- [Workflow Run](https://github.com/repo/actions/runs/123)
- [Evals Dashboard](https://example.com/evals/run/456)

"""
        assert body == expected

    def test_format_body_recent_best_drop(self):
        """Test format_body with recentBestDrop regression — exact string match."""
        regression = RecentBestDrop(kind='recentBestDrop', recent_best=4.2, current=3.5)
        payload = make_payload(regressions=[regression])
        body = format_body(payload, "https://github.com/repo/actions/runs/123", "https://example.com/evals/run/456")

        expected = """\
# Eval Regression Detected

## Summary

| Metric | Value |
|--------|-------|
| Cases | 30 |
| Graded | 28 |
| Errors | 2 |
| Mean Groundedness | 4.10 |
| Mean Coverage | 3.80 |
| Mean Score | 3.95 |
| P50 Latency (ms) | 1200 |
| P95 Latency (ms) | 2100 |
| Total Tokens (in+out) | 23000 |

## Regressions

- **Recent Best Drop**: 4.20 → 3.50

## Links

- [Workflow Run](https://github.com/repo/actions/runs/123)
- [Evals Dashboard](https://example.com/evals/run/456)

"""
        assert body == expected

    def test_format_body_harness_error_status(self):
        """Test format_body with harness error status — exact string match."""
        payload = make_payload(status='errored')
        body = format_body(payload, "https://github.com/repo/actions/runs/123", "https://example.com/evals/run/456")

        expected = """\
# Eval Regression Detected

⚠️ **Harness Error** — The eval harness failed to complete.

## Links

- [Workflow Run](https://github.com/repo/actions/runs/123)
- [Evals Dashboard](https://example.com/evals/run/456)

"""
        assert body == expected


class TestNotifyNoOp:
    """Tests for notify when there's nothing to report."""

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


class TestNotifyCreateIssue:
    """Tests for notify creating a new issue."""

    def test_notify_creates_issue_when_regression_exists(self, monkeypatch, tmp_path):
        """Test that notify creates an issue when a regression exists."""
        mock_run = Mock(spec=subprocess.run)
        monkeypatch.setattr('evals.notify.subprocess.run', mock_run)

        # Mock subprocess.run to return no open issues, then success
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

        # Should have 3 calls: list, label create, issue create
        assert mock_run.call_count == 3

        # Verify list call
        list_call = mock_run.call_args_list[0]
        assert list_call[0][0] == ['gh', 'issue', 'list', '--label', 'eval-regression', '--state', 'open', '--json', 'number', '--limit', '1']

        # Verify label create call
        label_call = mock_run.call_args_list[1]
        assert 'gh' in label_call[0][0]
        assert 'label' in label_call[0][0]
        assert 'create' in label_call[0][0]

        # Verify issue create call has --title
        create_call = mock_run.call_args_list[2]
        argv = create_call[0][0]
        assert argv[0:3] == ['gh', 'issue', 'create']
        assert '--label' in argv
        assert 'eval-regression' in argv
        assert '--title' in argv
        assert 'Eval regression: abc123d' in argv
        assert '--body' in argv

    def test_notify_issue_create_argv_exact(self, monkeypatch, tmp_path):
        """Test that gh issue create has exact expected argv."""
        mock_run = Mock(spec=subprocess.run)
        monkeypatch.setattr('evals.notify.subprocess.run', mock_run)

        mock_run.side_effect = [
            Mock(returncode=0, stdout='[]'),  # list
            Mock(returncode=0, stdout=''),     # label create
            Mock(returncode=0, stdout=''),     # issue create
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

        create_call = mock_run.call_args_list[2]
        argv = create_call[0][0]

        # Should be ['gh', 'issue', 'create', '--label', 'eval-regression', '--title', '<title>', '--body', '<body>']
        assert argv[0:3] == ['gh', 'issue', 'create']
        assert '--label' in argv
        assert 'eval-regression' in argv
        assert '--title' in argv
        assert '--body' in argv


class TestNotifyCommentOnExistingIssue:
    """Tests for notify commenting on existing issue."""

    def test_notify_comments_on_existing_issue(self, monkeypatch, tmp_path):
        """Test that notify comments on an existing issue when one is open."""
        mock_run = Mock(spec=subprocess.run)
        monkeypatch.setattr('evals.notify.subprocess.run', mock_run)

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

        # Should have 2 calls: list, comment
        assert mock_run.call_count == 2

        # Verify comment call
        comment_call = mock_run.call_args_list[1]
        argv = comment_call[0][0]
        assert argv[0:3] == ['gh', 'issue', 'comment']
        assert '42' in argv
        assert '--body' in argv

    def test_notify_comment_argv_exact(self, monkeypatch, tmp_path):
        """Test that gh issue comment has exact expected argv."""
        mock_run = Mock(spec=subprocess.run)
        monkeypatch.setattr('evals.notify.subprocess.run', mock_run)

        mock_run.side_effect = [
            Mock(returncode=0, stdout='[{"number": 42}]'),  # list
            Mock(returncode=0, stdout=''),                    # comment
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

        comment_call = mock_run.call_args_list[1]
        argv = comment_call[0][0]

        # Should be ['gh', 'issue', 'comment', '42', '--body', '<body>']
        assert argv[0:3] == ['gh', 'issue', 'comment']
        assert '42' in argv
        assert '--body' in argv


class TestNotifySubprocessFailures:
    """Tests for notify with subprocess failures."""

    def test_notify_gh_list_failure(self, monkeypatch, tmp_path, capsys):
        """Test that notify exits with non-zero when gh list fails."""
        mock_run = Mock(spec=subprocess.run)
        monkeypatch.setattr('evals.notify.subprocess.run', mock_run)

        mock_run.return_value = Mock(returncode=1, stderr='gh: error message')

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

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error listing issues" in captured.err

    def test_notify_gh_comment_failure(self, monkeypatch, tmp_path, capsys):
        """Test that notify exits with non-zero when gh comment fails."""
        mock_run = Mock(spec=subprocess.run)
        monkeypatch.setattr('evals.notify.subprocess.run', mock_run)

        mock_run.side_effect = [
            Mock(returncode=0, stdout='[{"number": 42}]'),  # list succeeds
            Mock(returncode=1, stderr='gh: comment error'),  # comment fails
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

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error commenting on issue" in captured.err

    def test_notify_gh_create_failure(self, monkeypatch, tmp_path, capsys):
        """Test that notify exits with non-zero when gh create fails."""
        mock_run = Mock(spec=subprocess.run)
        monkeypatch.setattr('evals.notify.subprocess.run', mock_run)

        mock_run.side_effect = [
            Mock(returncode=0, stdout='[]'),                # list succeeds (no issue)
            Mock(returncode=0, stdout=''),                   # label create
            Mock(returncode=1, stderr='gh: create error'),   # issue create fails
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

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error creating issue" in captured.err


class TestNotifyErrorHandling:
    """Tests for notify error handling with bad input."""

    def test_notify_missing_run_file_without_harness_error(self, tmp_path, capsys):
        """Test that notify exits with non-zero when run.json is missing and no --harness-error."""
        run_file = tmp_path / "run.json"  # File doesn't exist

        with pytest.raises(SystemExit) as exc_info:
            notify(
                run_file=str(run_file),
                run_url="https://github.com/repo/actions/runs/123",
                dashboard_url="https://example.com/evals/run/456",
                harness_error=False,
            )

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err.lower() or "error" in captured.err.lower()

    def test_notify_invalid_json_without_harness_error(self, tmp_path, capsys):
        """Test that notify exits with non-zero when run.json has invalid JSON."""
        run_file = tmp_path / "run.json"
        run_file.write_text('{ invalid json }')

        with pytest.raises(SystemExit) as exc_info:
            notify(
                run_file=str(run_file),
                run_url="https://github.com/repo/actions/runs/123",
                dashboard_url="https://example.com/evals/run/456",
                harness_error=False,
            )

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "invalid json" in captured.err.lower()

    def test_notify_invalid_schema_without_harness_error(self, tmp_path, capsys):
        """Test that notify exits with non-zero when run.json fails schema validation."""
        run_file = tmp_path / "run.json"
        run_file.write_text('{"run": null, "results": []}')  # Invalid schema

        with pytest.raises(SystemExit) as exc_info:
            notify(
                run_file=str(run_file),
                run_url="https://github.com/repo/actions/runs/123",
                dashboard_url="https://example.com/evals/run/456",
                harness_error=False,
            )

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "validation" in captured.err.lower() or "error" in captured.err.lower()

    def test_notify_harness_error_missing_run_file(self, monkeypatch, tmp_path):
        """Test that notify works with --harness-error even when run.json is missing."""
        mock_run = Mock(spec=subprocess.run)
        monkeypatch.setattr('evals.notify.subprocess.run', mock_run)

        mock_run.side_effect = [
            Mock(returncode=0, stdout='[]'),   # list
            Mock(returncode=0, stdout=''),      # label create
            Mock(returncode=0, stdout=''),      # issue create
        ]

        run_file = tmp_path / "run.json"  # File doesn't exist

        notify(
            run_file=str(run_file),
            run_url="https://github.com/repo/actions/runs/123",
            dashboard_url="https://example.com/evals/run/456",
            harness_error=True,
        )

        # Should still create an issue
        assert mock_run.call_count == 3
        create_call = mock_run.call_args_list[2]
        argv = create_call[0][0]
        assert '--title' in argv
        assert 'Eval harness error' in argv


class TestNotifyHarnessErrorBody:
    """Tests for notify with harness error status in payload."""

    def test_notify_payload_with_errored_status_and_no_flag(self, monkeypatch, tmp_path):
        """Test that notify creates issue when payload status is errored (no --harness-error flag)."""
        mock_run = Mock(spec=subprocess.run)
        monkeypatch.setattr('evals.notify.subprocess.run', mock_run)

        mock_run.side_effect = [
            Mock(returncode=0, stdout='[]'),   # list
            Mock(returncode=0, stdout=''),      # label create
            Mock(returncode=0, stdout=''),      # issue create
        ]

        run_file = tmp_path / "run.json"
        payload = make_payload(status='errored')
        run_file.write_text(payload.model_dump_json())

        notify(
            run_file=str(run_file),
            run_url="https://github.com/repo/actions/runs/123",
            dashboard_url="https://example.com/evals/run/456",
            harness_error=False,  # No flag, but status is errored
        )

        # Should create issue because status is errored
        assert mock_run.call_count == 3


class TestMainCliEntrypoint:
    """Tests for main() CLI entrypoint."""

    def test_main_with_all_args(self, monkeypatch, tmp_path):
        """Test main() CLI entrypoint with all arguments."""
        mock_notify = Mock()
        monkeypatch.setattr('evals.notify.notify', mock_notify)
        monkeypatch.setattr('sys.argv', [
            'evals.notify',
            '--run', '/tmp/run.json',
            '--run-url', 'https://github.com/repo/actions/runs/123',
            '--dashboard-url', 'https://example.com/evals/run/456',
            '--harness-error',
        ])

        main()

        mock_notify.assert_called_once()
        call_kwargs = mock_notify.call_args[1]
        assert call_kwargs['run_file'] == '/tmp/run.json'
        assert call_kwargs['run_url'] == 'https://github.com/repo/actions/runs/123'
        assert call_kwargs['dashboard_url'] == 'https://example.com/evals/run/456'
        assert call_kwargs['harness_error'] is True

    def test_main_with_required_args_only(self, monkeypatch):
        """Test main() CLI entrypoint with required args only."""
        mock_notify = Mock()
        monkeypatch.setattr('evals.notify.notify', mock_notify)
        monkeypatch.setattr('sys.argv', [
            'evals.notify',
            '--run', '/tmp/run.json',
            '--run-url', 'https://github.com/repo/actions/runs/123',
        ])

        main()

        mock_notify.assert_called_once()
        call_kwargs = mock_notify.call_args[1]
        assert call_kwargs['run_file'] == '/tmp/run.json'
        assert call_kwargs['run_url'] == 'https://github.com/repo/actions/runs/123'
        assert call_kwargs['dashboard_url'] is None
        assert call_kwargs['harness_error'] is False

    def test_main_end_to_end_with_regression(self, monkeypatch, tmp_path):
        """Test main() end to end with stubbed subprocess."""
        mock_run = Mock(spec=subprocess.run)
        monkeypatch.setattr('evals.notify.subprocess.run', mock_run)

        mock_run.side_effect = [
            Mock(returncode=0, stdout='[]'),   # list
            Mock(returncode=0, stdout=''),      # label create
            Mock(returncode=0, stdout=''),      # issue create
        ]

        run_file = tmp_path / "run.json"
        regression = MeanScoreDrop(kind='meanScoreDrop', baseline=4.0, current=3.5)
        payload = make_payload(regressions=[regression])
        run_file.write_text(payload.model_dump_json())

        monkeypatch.setattr('sys.argv', [
            'evals.notify',
            '--run', str(run_file),
            '--run-url', 'https://github.com/repo/actions/runs/123',
        ])

        main()

        # Should have called subprocess.run for list, label, and create
        assert mock_run.call_count == 3
