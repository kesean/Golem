"""
Regression notifier for eval harness.

When a scheduled run has regressions or exits 1, opens a GitHub issue labelled
`eval-regression`. If one is already open, comments on that issue instead.

The `gh` CLI is used via subprocess; it operates on the current repo from the
GitHub Actions checkout (no --repo needed).
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import pydantic

from evals.models import EvalRunPayload


def _sanitize_value(value: str) -> str:
    """Sanitize value by replacing interior backticks with single quotes."""
    return value.replace('`', "'")


def _dashboard_link(dashboard_url: Optional[str], run_id: Optional[str]) -> Optional[str]:
    """Append ?run=<id> (URL-encoded) to the dashboard URL when both are present."""
    if not dashboard_url:
        return dashboard_url
    if not run_id:
        return dashboard_url
    sep = '&' if '?' in dashboard_url else '?'
    return f"{dashboard_url}{sep}run={quote(str(run_id), safe='')}"


def format_body(payload: EvalRunPayload, run_url: str, dashboard_url: Optional[str] = None, harness_error: bool = False) -> str:
    """
    Format the GitHub issue body with summary table and regressions.

    Args:
        payload: The eval run payload with run summary and regressions.
        run_url: URL to the workflow run (e.g., GitHub Actions run).
        dashboard_url: Optional URL to the evals dashboard for this run.
        harness_error: If True, add harness error banner even if status is not errored.

    Returns:
        Markdown-formatted body text for the GitHub issue.
    """
    lines = []

    # Check if harness errored or harness_error flag is set
    is_harness_error = payload.run.status == 'errored' or harness_error

    # Title/header
    lines.append("# Eval Harness Error" if is_harness_error else "# Eval Regression Detected")
    lines.append("")

    if is_harness_error:
        lines.append("⚠️ **Harness Error** — The eval harness failed to complete.")
        lines.append("")

    # Add summary table if not errored
    if payload.run.status != 'errored':
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
                case_id = _sanitize_value(regression.case_id)
                rule = _sanitize_value(str(regression.rule))
                lines.append(f"- **Rule Flip** (`{rule}`): case `{case_id}`")
            elif regression.kind == 'caseScoreDrop':
                case_id = _sanitize_value(regression.case_id)
                lines.append(f"- **Case Score Drop**: `{case_id}` — {regression.baseline:.2f} → {regression.current:.2f}")
            elif regression.kind == 'errorRate':
                error_pct = (regression.error_count / regression.case_count * 100) if regression.case_count > 0 else 0
                lines.append(f"- **Error Rate**: {regression.error_count}/{regression.case_count} cases ({error_pct:.1f}%)")
            elif regression.kind == 'recentBestDrop':
                lines.append(f"- **Recent Best Drop**: {regression.recent_best:.2f} → {regression.current:.2f}")
            else:
                # Generic fallback for unknown regression kinds
                lines.append(f"- **{regression.kind}**: {regression}")

        lines.append("")

    # Links
    lines.append("## Links")
    lines.append("")
    lines.append(f"- [Workflow Run]({run_url})")
    if dashboard_url:
        lines.append(f"- [Evals Dashboard]({dashboard_url})")

    return "\n".join(lines) + "\n\n"


def format_body_no_payload(run_url: str, dashboard_url: Optional[str] = None) -> str:
    """
    Format the GitHub issue body when there is no valid payload (harness error).

    Args:
        run_url: URL to the workflow run.
        dashboard_url: Optional URL to the evals dashboard.

    Returns:
        Markdown-formatted body text for the GitHub issue.
    """
    body_lines = [
        "# Eval Harness Error",
        "",
        "⚠️ **Harness Error** — The eval harness failed to complete.",
        "",
        "## Links",
        "",
        f"- [Workflow Run]({run_url})",
    ]
    if dashboard_url:
        body_lines.append(f"- [Evals Dashboard]({dashboard_url})")
    return "\n".join(body_lines) + "\n\n"


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
    git_sha = None
    run_id = None

    # Load payload from file
    if Path(run_file).exists():
        try:
            with open(run_file, 'r') as f:
                data = json.load(f)

            # Ensure data is a dict
            if not isinstance(data, dict):
                if not harness_error:
                    print(f"Error: run.json is not a valid object", file=sys.stderr)
                    sys.exit(1)
                payload = None
            else:
                # run.py writes the Convex run id at run.runId (ignored by the model)
                run_data = data.get('run')
                if isinstance(run_data, dict):
                    run_id = run_data.get('runId')
                payload = EvalRunPayload.model_validate(data)
                has_regressions = bool(payload.run.regressions)
                git_sha = payload.run.git_sha
        except json.JSONDecodeError as e:
            if not harness_error:
                print(f"Error: run.json has invalid JSON: {e}", file=sys.stderr)
                sys.exit(1)
            payload = None
        except pydantic.ValidationError as e:
            if not harness_error:
                print(f"Error: run.json schema validation failed: {e}", file=sys.stderr)
                sys.exit(1)
            payload = None
        except OSError as e:
            if not harness_error:
                print(f"Error: could not read run.json: {e}", file=sys.stderr)
                sys.exit(1)
            payload = None
    elif not harness_error:
        print(f"Error: run.json not found: {run_file}", file=sys.stderr)
        sys.exit(1)

    # Check if we should notify
    should_notify = harness_error or has_regressions or (
        payload and payload.run.status == 'errored'
    )

    if not should_notify:
        return  # Nothing to notify about

    dashboard_url = _dashboard_link(dashboard_url, run_id)

    # Get or create the body and title
    if payload:
        body = format_body(payload, run_url, dashboard_url, harness_error=harness_error)
        git_sha = payload.run.git_sha
        if harness_error:
            title = "Eval harness error"
        else:
            title = f"Eval regression: {git_sha[:7]}"
    else:
        # Harness error without payload
        body = format_body_no_payload(run_url, dashboard_url)
        title = "Eval harness error"

    # Check for existing open issue
    try:
        result = subprocess.run(
            ['gh', 'issue', 'list', '--label', 'eval-regression', '--state', 'open', '--json', 'number', '--limit', '1'],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            if 'not found' in result.stderr.lower() or 'not installed' in result.stderr.lower():
                print("Error: gh CLI not found or not in PATH", file=sys.stderr)
            else:
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

            # Create new issue with title
            create_result = subprocess.run(
                ['gh', 'issue', 'create', '--label', 'eval-regression', '--title', title, '--body', body],
                capture_output=True,
                text=True,
                check=False,
            )

            if create_result.returncode != 0:
                print(f"Error creating issue: {create_result.stderr}", file=sys.stderr)
                sys.exit(1)

    except FileNotFoundError:
        print("Error: gh CLI not found", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: gh returned invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """CLI entrypoint for the regression notifier."""
    parser = argparse.ArgumentParser(
        description='Open or comment on eval-regression GitHub issue when regressions are detected.',
    )
    parser.add_argument(
        '--run',
        required=True,
        help='Path to eval-out/run.json',
    )
    parser.add_argument(
        '--run-url',
        required=True,
        help='URL to the workflow run (e.g., GitHub Actions run)',
    )
    parser.add_argument(
        '--dashboard-url',
        default=None,
        help='Optional URL to the evals dashboard',
    )
    parser.add_argument(
        '--harness-error',
        action='store_true',
        help='Notify even if run.json is missing or invalid',
    )

    args = parser.parse_args()

    notify(
        run_file=args.run,
        run_url=args.run_url,
        dashboard_url=args.dashboard_url,
        harness_error=args.harness_error,
    )


if __name__ == '__main__':
    main()
