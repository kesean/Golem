"""
Summary computation and regression detection for eval runs.
"""

import math
from evals.models import (
    CaseResult, RunSummary, Regression,
    MeanScoreDrop, RuleFlip, CaseScoreDrop, ErrorRate, RecentBestDrop,
)

# Thresholds and constants
MEAN_SCORE_DROP = 0.3
CASE_SCORE_DROP = 2
MAX_ERROR_RATE = 0.2
RECENT_BEST_DROP = 0.5


def summarize(results: list[CaseResult]) -> RunSummary:
    """
    Compute a RunSummary from a list of case results.

    Ungraded cases (where judge is None) are excluded from mean calculations.
    For empty input or zero graded cases, means are 0.0.
    p50 and p95 use nearest-rank percentile (rank = ceil(p/100 × n), 1-indexed).
    """
    case_count = len(results)
    error_count = sum(1 for r in results if r.error is not None)
    graded_results = [r for r in results if r.judge is not None]
    graded_count = len(graded_results)

    # Compute means over graded cases (or 0.0 if none)
    if graded_count > 0:
        mean_groundedness = sum(r.judge.groundedness for r in graded_results) / graded_count
        mean_coverage = sum(r.judge.coverage for r in graded_results) / graded_count
        case_scores = [(r.judge.groundedness + r.judge.coverage) / 2 for r in graded_results]
        mean_score = sum(case_scores) / graded_count
    else:
        mean_groundedness = 0.0
        mean_coverage = 0.0
        mean_score = 0.0

    # Compute rule pass rates over all cases
    rule_pass_rate = {}
    rule_names = ["completed", "format", "product_tag", "citations", "retrieval"]
    for rule_name in rule_names:
        passes = sum(1 for r in results if getattr(r.rules, rule_name, False))
        rate = passes / case_count if case_count > 0 else 0.0
        rule_pass_rate[rule_name] = rate

    # Compute p50 and p95 latencies using nearest-rank percentile
    latencies = sorted([r.latency_ms for r in results])

    def nearest_rank_percentile(sorted_list: list[float], percentile: float) -> float:
        """Nearest-rank percentile: rank = ceil(p/100 * n), 1-indexed."""
        if not sorted_list:
            return 0.0
        n = len(sorted_list)
        rank = math.ceil(percentile / 100.0 * n)
        # Convert 1-indexed rank to 0-indexed
        index = rank - 1
        # Clamp to valid range
        index = max(0, min(index, n - 1))
        return float(sorted_list[index])

    p50_latency_ms = nearest_rank_percentile(latencies, 50.0) if latencies else 0.0
    p95_latency_ms = nearest_rank_percentile(latencies, 95.0) if latencies else 0.0

    # Sum tokens
    total_input_tokens = sum(r.input_tokens for r in results)
    total_output_tokens = sum(r.output_tokens for r in results)

    return RunSummary(
        case_count=case_count,
        graded_count=graded_count,
        error_count=error_count,
        mean_groundedness=mean_groundedness,
        mean_coverage=mean_coverage,
        mean_score=mean_score,
        rule_pass_rate=rule_pass_rate,
        p50_latency_ms=p50_latency_ms,
        p95_latency_ms=p95_latency_ms,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
    )


def find_regressions(
    current: list[CaseResult],
    summary: RunSummary,
    baseline: tuple[RunSummary, list[CaseResult]] | None,
    recent_best: float | None,
) -> list[Regression]:
    """
    Detect regressions in the current run compared to the baseline.

    Regression kinds:
    (a) meanScoreDrop: mean judge score drops by more than 0.3
    (b) ruleFlip: a rule check that passed for a case in baseline fails now (graded cases only)
    (c) caseScoreDrop: a case's judge score drops by >= 2 (graded cases only)
    (d) errorRate: more than 20% of cases error
    (e) recentBestDrop: mean score is more than 0.5 below recent_best (skipped if recent_best is None)

    When there is no baseline, regressions are empty.
    """
    regressions: list[Regression] = []

    if baseline is None:
        return regressions

    baseline_summary, baseline_results = baseline

    # Build a map of case_id -> CaseResult for baseline
    baseline_by_case_id = {r.case_id: r for r in baseline_results}

    # (a) meanScoreDrop: drop by more than 0.3
    if summary.mean_score < baseline_summary.mean_score - MEAN_SCORE_DROP:
        regressions.append(
            MeanScoreDrop(
                kind="meanScoreDrop",
                baseline=baseline_summary.mean_score,
                current=summary.mean_score,
            )
        )

    # (b) ruleFlip: for graded cases, check if any rule passed in baseline but fails now
    current_graded = {r.case_id: r for r in current if r.judge is not None}
    for case_id, current_case in current_graded.items():
        baseline_case = baseline_by_case_id.get(case_id)
        if baseline_case is None or baseline_case.judge is None:
            # Case missing from baseline or ungraded in baseline; skip
            continue

        # Check each rule
        rule_names = ["completed", "format", "product_tag", "citations", "retrieval"]
        for rule_name in rule_names:
            baseline_passed = getattr(baseline_case.rules, rule_name, False)
            current_passed = getattr(current_case.rules, rule_name, False)

            if baseline_passed and not current_passed:
                regressions.append(
                    RuleFlip(
                        kind="ruleFlip",
                        case_id=case_id,
                        rule=rule_name,
                    )
                )

    # (c) caseScoreDrop: for graded cases, check if judge score drops by >= 2
    for case_id, current_case in current_graded.items():
        baseline_case = baseline_by_case_id.get(case_id)
        if baseline_case is None or baseline_case.judge is None:
            # Case missing from baseline or ungraded in baseline; skip
            continue

        baseline_score = (baseline_case.judge.groundedness + baseline_case.judge.coverage) / 2
        current_score = (current_case.judge.groundedness + current_case.judge.coverage) / 2

        if baseline_score - current_score >= CASE_SCORE_DROP:
            regressions.append(
                CaseScoreDrop(
                    kind="caseScoreDrop",
                    case_id=case_id,
                    baseline=baseline_score,
                    current=current_score,
                )
            )

    # (d) errorRate: more than 20% of cases error
    if summary.case_count > 0:
        error_rate = summary.error_count / summary.case_count
        if error_rate > MAX_ERROR_RATE:
            regressions.append(
                ErrorRate(
                    kind="errorRate",
                    error_count=summary.error_count,
                    case_count=summary.case_count,
                )
            )

    # (e) recentBestDrop: mean score more than 0.5 below recent_best
    if recent_best is not None and summary.mean_score < recent_best - RECENT_BEST_DROP:
        regressions.append(
            RecentBestDrop(
                kind="recentBestDrop",
                recent_best=recent_best,
                current=summary.mean_score,
            )
        )

    return regressions
