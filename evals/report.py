"""
evals/report.py — Report generation for eval runs.

Generates Markdown reports with:
- Run summary (scores, pass rates, tokens)
- Regressions (if any)
- Worst 5 cases
"""

from typing import Optional
from evals.models import Run, CaseResult, RunSummary, Regression


def generate_report(
    run: Run,
    results: list[CaseResult],
    baseline: Optional[tuple[RunSummary, list[CaseResult]]] = None,
) -> str:
    """
    Generate a Markdown report for an eval run.

    Args:
        run: The Run object with summary and regressions
        results: List of CaseResult objects
        baseline: Optional (baseline_summary, baseline_results) tuple

    Returns:
        Markdown report string
    """
    lines = []

    # Title
    lines.append(f"# Eval Run Report")
    lines.append("")

    # Run metadata
    lines.append("## Run Metadata")
    lines.append(f"- **Label**: {run.label}")
    lines.append(f"- **Status**: {run.status}")
    lines.append(f"- **Git SHA**: `{run.git_sha[:7]}`")
    lines.append(f"- **Git Ref**: {run.git_ref}")
    lines.append(f"- **App Model**: {run.app_model}")
    lines.append(f"- **Judge Model**: {run.judge_model}")
    lines.append(f"- **Cases Version**: {run.cases_version}")
    lines.append("")

    # Summary section
    summary = run.summary
    lines.append("## Summary")
    lines.append(f"- **Cases**: {summary.case_count}")
    lines.append(f"- **Graded**: {summary.graded_count}")
    lines.append(f"- **Errors**: {summary.error_count}")
    lines.append(f"- **Mean Groundedness**: {summary.mean_groundedness:.2f}/5")
    lines.append(f"- **Mean Coverage**: {summary.mean_coverage:.2f}/5")
    lines.append(f"- **Mean Score**: {summary.mean_score:.2f}")
    lines.append(f"- **P50 Latency**: {summary.p50_latency_ms:.0f}ms")
    lines.append(f"- **P95 Latency**: {summary.p95_latency_ms:.0f}ms")
    lines.append(f"- **Total Input Tokens**: {summary.total_input_tokens:,}")
    lines.append(f"- **Total Output Tokens**: {summary.total_output_tokens:,}")
    lines.append("")

    # Rule pass rates
    lines.append("### Rule Pass Rates")
    # Access rule_pass_rate fields using getattr (RulePassRate model)
    rule_names = ["completed", "format", "product_tag", "citations", "retrieval"]
    for rule_name in rule_names:
        rate = getattr(summary.rule_pass_rate, rule_name, 0.0)
        lines.append(f"- **{rule_name}**: {rate * 100:.1f}%")
    lines.append("")

    # Regressions section
    if run.regressions:
        lines.append("## Regressions Detected ⚠️")
        lines.append("")
        for i, regression in enumerate(run.regressions, 1):
            lines.extend(_format_regression(regression))
            lines.append("")
    else:
        if baseline:
            lines.append("## No Regressions ✓")
            lines.append("")
        else:
            lines.append("## No Baseline")
            lines.append("No baseline available for comparison.")
            lines.append("")

    # Worst 5 cases (graded cases, sorted by score)
    graded_results = [r for r in results if r.judge is not None]
    if graded_results:
        graded_results_sorted = sorted(
            graded_results,
            key=lambda r: (r.judge.groundedness + r.judge.coverage) / 2,
        )

        worst_5 = graded_results_sorted[:5]

        lines.append("## Worst 5 Cases")
        lines.append("")

        for idx, result in enumerate(worst_5, 1):
            score = (result.judge.groundedness + result.judge.coverage) / 2
            lines.append(f"### {idx}. {result.case_id}")
            lines.append(f"**Score**: {score:.1f} (G:{result.judge.groundedness} C:{result.judge.coverage})")
            lines.append(f"**Question**: {result.question[:80]}...")
            lines.append(f"**Reason**: {result.judge.reason}")
            lines.append(f"**Missed Key Points**: {', '.join(result.judge.key_points_missed) if result.judge.key_points_missed else 'None'}")
            lines.append("")

    return "\n".join(lines)


def _format_regression(regression: Regression) -> list[str]:
    """Format a single regression as Markdown lines."""
    lines = []

    if regression.kind == "meanScoreDrop":
        lines.append(f"**Mean Score Drop**: {regression.baseline:.2f} → {regression.current:.2f}")
        lines.append(f"Drop: {regression.baseline - regression.current:.2f}")

    elif regression.kind == "ruleFlip":
        lines.append(f"**Rule Flip**: Case `{regression.case_id}`")
        lines.append(f"Rule `{regression.rule}` passed in baseline but failed now")

    elif regression.kind == "caseScoreDrop":
        lines.append(f"**Case Score Drop**: Case `{regression.case_id}`")
        lines.append(f"Score: {regression.baseline:.1f} → {regression.current:.1f}")
        lines.append(f"Drop: {regression.baseline - regression.current:.1f}")

    elif regression.kind == "errorRate":
        rate = (regression.error_count / regression.case_count) * 100 if regression.case_count > 0 else 0
        lines.append(f"**High Error Rate**: {regression.error_count}/{regression.case_count} cases errored ({rate:.1f}%)")

    elif regression.kind == "recentBestDrop":
        lines.append(f"**Recent Best Drop**: Mean score {regression.current:.2f} vs recent best {regression.recent_best:.2f}")
        lines.append(f"Below recent best by {regression.recent_best - regression.current:.2f}")

    return lines
