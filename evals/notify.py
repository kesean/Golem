"""
Regression notifier for eval harness.

When a scheduled run has regressions or exits 1, opens a GitHub issue labelled
`eval-regression`. If one is already open, comments on that issue instead.
"""

import json
import sys
import subprocess
from pathlib import Path
from typing import Optional

from evals.models import EvalRunPayload, Regression


def format_body(payload: EvalRunPayload, run_url: str, dashboard_url: Optional[str] = None) -> str:
    """
    Format the GitHub issue body with summary table and regressions.

    Args:
        payload: The eval run payload with run summary and regressions.
        run_url: URL to the workflow run (e.g., GitHub Actions run).
        dashboard_url: Optional URL to the evals dashboard for this run.

    Returns:
        Markdown-formatted body text for the GitHub issue.
    """
    lines = []

    # Title/header
    lines.append("# Eval Regression Detected")
    lines.append("")

    # Check if harness errored
    if payload.run.status == 'errored':
        lines.append("⚠️ **Harness Error** — The eval harness failed to complete.")
        lines.append("")
    else:
        # Add summary table if not errored
        summary = payload.run.summary
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Cases | {summary.case_count} |")
        lines.append(f"| Graded | {summary.graded_count} |")
        lines.append(f"| Errors | {summary.error_count} |")
        lines.append(f"| Mean Groundedness | {summary.mean_groundedness:.2f} |")
        lines.append(f"| Mean Coverage | {summary.mean_coverage:.2f} |")
        lines.append(f"| Mean Score | {summary.mean_score:.2f} |")
        lines.append(f"| P50 Latency (ms) | {summary.p50_latency_ms:.0f} |")
        lines.append(f"| P95 Latency (ms) | {summary.p95_latency_ms:.0f} |")
        lines.append(f"| Total Tokens (in+out) | {summary.total_input_tokens + summary.total_output_tokens} |")
        lines.append("")

    # Regressions section
    if payload.run.regressions:
        lines.append("## Regressions")
        lines.append("")

        for regression in payload.run.regressions:
            if regression.kind == 'meanScoreDrop':
                lines.append(f"- **Mean Score Drop**: {regression.baseline:.2f} → {regression.current:.2f}")
            elif regression.kind == 'ruleFlip':
                lines.append(f"- **Rule Flip** (`{regression.rule}`): case `{regression.case_id}`")
            elif regression.kind == 'caseScoreDrop':
                lines.append(f"- **Case Score Drop**: `{regression.case_id}` — {regression.baseline:.2f} → {regression.current:.2f}")
            elif regression.kind == 'errorRate':
                error_pct = (regression.error_count / regression.case_count * 100) if regression.case_count > 0 else 0
                lines.append(f"- **Error Rate**: {regression.error_count}/{regression.case_count} cases ({error_pct:.1f}%)")
            elif regression.kind == 'recentBestDrop':
                lines.append(f"- **Recent Best Drop**: {regression.recent_best:.2f} → {regression.current:.2f}")

        lines.append("")

    # Links
    lines.append("## Links")
    lines.append("")
    lines.append(f"- [Workflow Run]({run_url})")
    if dashboard_url:
        lines.append(f"- [Evals Dashboard]({dashboard_url})")

    lines.append("")

    return "\n".join(lines)


def notify(
    run_file: str,
    run_url: str,
    dashboard_url: Optional[str] = None,
    harness_error: bool = False,
) -> None:
    """
    Open or comment on an eval-regression GitHub issue.

    When a scheduled run has regressions or exits 1, opens a GitHub issue labelled
    `eval-regression`. If one is already open, comments on that issue instead.

    Args:
        run_file: Path to eval-out/run.json (EvalRunPayload + runId field).
        run_url: URL to the workflow run.
        dashboard_url: Optional URL to the evals dashboard.
        harness_error: If True, notify even if run.json is missing/invalid.

    Raises:
        SystemExit: With non-zero code if subprocess call fails.
    """
    payload = None
    has_regressions = False

    # Load payload from file
    if Path(run_file).exists():
        try:
            with open(run_file, 'r') as f:
                data = json.load(f)
            # Handle extra 'runId' field if present
            if 'runId' in data:
                runId = data.pop('runId')
            payload = EvalRunPayload.model_validate(data)
            has_regressions = bool(payload.run.regressions)
        except Exception as e:
            if not harness_error:
                raise
            # If harness_error flag is set, we can proceed without a valid payload
            payload = None
    elif not harness_error:
        raise FileNotFoundError(f"Run file not found: {run_file}")

    # Check if we should notify
    should_notify = harness_error or has_regressions or (
        payload and payload.run.status == 'errored'
    )

    if not should_notify:
        return  # Nothing to notify about

    # Get or create the body
    if payload:
        body = format_body(payload, run_url, dashboard_url)
    else:
        body = "# Eval Harness Error\n\nThe eval harness failed to complete.\n\n## Links\n\n" + \
               f"- [Workflow Run]({run_url})"
        if dashboard_url:
            body += f"\n- [Evals Dashboard]({dashboard_url})"

    # Check for existing open issue
    try:
        result = subprocess.run(
            ['gh', 'issue', 'list', '--label', 'eval-regression', '--state', 'open', '--json', 'number', '--limit', '1'],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            print(f"Error listing issues: {result.stderr}", file=sys.stderr)
            sys.exit(1)

        issues = json.loads(result.stdout)

        if issues:
            # Comment on existing issue
            issue_number = issues[0]['number']
            comment_result = subprocess.run(
                ['gh', 'issue', 'comment', str(issue_number), '--body', body],
                capture_output=True,
                text=True,
                check=False,
            )

            if comment_result.returncode != 0:
                print(f"Error commenting on issue: {comment_result.stderr}", file=sys.stderr)
                sys.exit(1)
        else:
            # Create new issue (with label)
            # First, try to create the label if it doesn't exist
            label_result = subprocess.run(
                ['gh', 'label', 'create', 'eval-regression',
                 '--color', 'ff0000',
                 '--description', 'Eval harness detected a regression',
                 '--force'],
                capture_output=True,
                text=True,
                check=False,
            )

            # Even if label creation fails (already exists), continue to create issue

            # Create new issue
            create_result = subprocess.run(
                ['gh', 'issue', 'create', '--label', 'eval-regression', '--body', body],
                capture_output=True,
                text=True,
                check=False,
            )

            if create_result.returncode != 0:
                print(f"Error creating issue: {create_result.stderr}", file=sys.stderr)
                sys.exit(1)

    except Exception as e:
        print(f"Notification failed: {e}", file=sys.stderr)
        sys.exit(1)
