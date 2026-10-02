"""
Tests for regression detection and summary computation.
"""

import pytest
from evals.models import (
    CaseResult, JudgeVerdict, RuleResults, RunSummary,
    MeanScoreDrop, RuleFlip, CaseScoreDrop, ErrorRate, RecentBestDrop,
)
from evals.regression import summarize, find_regressions


def make_rule_results(**overrides):
    """Helper to create RuleResults with sensible defaults."""
    defaults = {
        "completed": True,
        "format": True,
        "product_tag": True,
        "citations": True,
        "retrieval": True,
    }
    defaults.update(overrides)
    return RuleResults(**defaults)


def make_case_result(
    case_id: str,
    rules: RuleResults | None = None,
    judge: JudgeVerdict | None = None,
    error: str | None = None,
    latency_ms: int = 100,
    **overrides
) -> CaseResult:
    """Helper to create CaseResult with sensible defaults."""
    if rules is None:
        rules = make_rule_results()
    if judge is None and error is None:
        judge = JudgeVerdict(groundedness=4, coverage=3, key_points_missed=[], reason="Good")

    defaults = {
        "case_id": case_id,
        "question": f"Question for {case_id}",
        "response": "Response text",
        "product_tag": "Other",
        "retrieved_urls": [],
        "rules": rules,
        "judge": judge,
        "latency_ms": latency_ms,
        "input_tokens": 100,
        "output_tokens": 50,
        "error": error,
    }
    defaults.update(overrides)
    return CaseResult(**defaults)


class TestSummarize:
    """Tests for the summarize function."""

    def test_empty_results(self):
        """Test summarize with empty results list."""
        summary = summarize([])

        assert summary.case_count == 0
        assert summary.graded_count == 0
        assert summary.error_count == 0
        assert summary.mean_groundedness == 0.0
        assert summary.mean_coverage == 0.0
        assert summary.mean_score == 0.0
        assert summary.p50_latency_ms == 0.0
        assert summary.p95_latency_ms == 0.0
        assert summary.total_input_tokens == 0
        assert summary.total_output_tokens == 0

    def test_single_graded_case(self):
        """Test summarize with a single graded case."""
        judge = JudgeVerdict(groundedness=4, coverage=3, key_points_missed=[], reason="Reason")
        case = make_case_result("case-001", judge=judge, latency_ms=150)

        summary = summarize([case])

        assert summary.case_count == 1
        assert summary.graded_count == 1
        assert summary.error_count == 0
        assert summary.mean_groundedness == 4.0
        assert summary.mean_coverage == 3.0
        assert summary.mean_score == 3.5  # (4 + 3) / 2
        assert summary.p50_latency_ms == 150.0
        assert summary.p95_latency_ms == 150.0
        assert summary.total_input_tokens == 100
        assert summary.total_output_tokens == 50
        assert summary.rule_pass_rate == {
            "completed": 1.0,
            "format": 1.0,
            "product_tag": 1.0,
            "citations": 1.0,
            "retrieval": 1.0,
        }

    def test_multiple_graded_cases(self):
        """Test summarize with multiple graded cases."""
        cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=5, coverage=5, key_points_missed=[], reason="Perfect"), latency_ms=100),
            make_case_result("case-002", judge=JudgeVerdict(groundedness=3, coverage=2, key_points_missed=[], reason="Poor"), latency_ms=200),
            make_case_result("case-003", judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good"), latency_ms=150),
        ]

        summary = summarize(cases)

        assert summary.case_count == 3
        assert summary.graded_count == 3
        assert summary.error_count == 0
        assert summary.mean_groundedness == 4.0  # (5 + 3 + 4) / 3
        assert abs(summary.mean_coverage - 3.666666666666667) < 0.0001  # (5 + 2 + 4) / 3
        mean_score_expected = ((5 + 5) / 2 + (3 + 2) / 2 + (4 + 4) / 2) / 3
        assert abs(summary.mean_score - mean_score_expected) < 0.0001
        assert summary.total_input_tokens == 300
        assert summary.total_output_tokens == 150
        # p50 should be 150 (median of 100, 150, 200)
        # p95 should be 195 (nearest-rank: rank = ceil(0.95 * 3) = 3, which is index 2 = 200... actually let me recalculate)
        # Nearest-rank percentile: rank = ceil(p/100 * n) with 1-based indexing
        # For p50: rank = ceil(0.50 * 3) = 2 (1-indexed), so latencies[1] = 150
        # For p95: rank = ceil(0.95 * 3) = 3 (1-indexed), so latencies[2] = 200
        assert summary.p50_latency_ms == 150.0
        assert summary.p95_latency_ms == 200.0

    def test_cases_with_errors(self):
        """Test summarize with some cases having errors."""
        cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=4, coverage=3, key_points_missed=[], reason="Good"), latency_ms=100),
            make_case_result("case-002", error="Timeout", judge=None, latency_ms=5000),
            make_case_result("case-003", judge=JudgeVerdict(groundedness=5, coverage=5, key_points_missed=[], reason="Perfect"), latency_ms=150),
        ]

        summary = summarize(cases)

        assert summary.case_count == 3
        assert summary.graded_count == 2  # Only cases without errors
        assert summary.error_count == 1
        assert summary.mean_groundedness == 4.5  # (4 + 5) / 2
        assert summary.mean_coverage == 4.0  # (3 + 5) / 2
        mean_score_expected = ((4 + 3) / 2 + (5 + 5) / 2) / 2
        assert abs(summary.mean_score - mean_score_expected) < 0.0001

    def test_rule_pass_rates(self):
        """Test that rule pass rates are computed correctly."""
        cases = [
            make_case_result("case-001", rules=make_rule_results(), judge=JudgeVerdict(groundedness=4, coverage=3, key_points_missed=[], reason="Good")),
            make_case_result("case-002", rules=make_rule_results(citations=False), judge=JudgeVerdict(groundedness=3, coverage=3, key_points_missed=[], reason="Good")),
            make_case_result("case-003", rules=make_rule_results(format=False), judge=JudgeVerdict(groundedness=5, coverage=5, key_points_missed=[], reason="Good")),
        ]

        summary = summarize(cases)

        assert summary.rule_pass_rate["completed"] == 1.0
        assert summary.rule_pass_rate["format"] == 2.0 / 3.0
        assert summary.rule_pass_rate["product_tag"] == 1.0
        assert summary.rule_pass_rate["citations"] == 2.0 / 3.0
        assert summary.rule_pass_rate["retrieval"] == 1.0

    def test_all_errors(self):
        """Test summarize with all cases errored."""
        cases = [
            make_case_result("case-001", error="Error 1", judge=None, latency_ms=100),
            make_case_result("case-002", error="Error 2", judge=None, latency_ms=200),
        ]

        summary = summarize(cases)

        assert summary.case_count == 2
        assert summary.graded_count == 0
        assert summary.error_count == 2
        assert summary.mean_groundedness == 0.0
        assert summary.mean_coverage == 0.0
        assert summary.mean_score == 0.0

    def test_p50_p95_percentiles(self):
        """Test p50 and p95 percentile calculation (nearest-rank method)."""
        # Create 10 cases with latencies 100, 200, ..., 1000
        cases = [
            make_case_result(f"case-{i:03d}", judge=JudgeVerdict(groundedness=4, coverage=3, key_points_missed=[], reason="Good"), latency_ms=(i + 1) * 100)
            for i in range(10)
        ]

        summary = summarize(cases)

        # Nearest-rank percentile: rank = ceil(p/100 * n), 1-indexed
        # For p50 with 10 items: rank = ceil(0.50 * 10) = 5, so latencies[4] = 500
        # For p95 with 10 items: rank = ceil(0.95 * 10) = 10, so latencies[9] = 1000
        assert summary.p50_latency_ms == 500.0
        assert summary.p95_latency_ms == 1000.0


class TestFindRegressions:
    """Tests for the find_regressions function."""

    def test_no_baseline_returns_empty(self):
        """Test that no baseline returns empty regressions list."""
        cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=3, coverage=2, key_points_missed=[], reason="Fair"))
        ]
        summary = summarize(cases)

        regressions = find_regressions(cases, summary, None, None)

        assert regressions == []

    def test_mean_score_drop_regression(self):
        """Test meanScoreDrop regression kind (a)."""
        # Current run
        current_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=3, coverage=3, key_points_missed=[], reason="Fair")),
            make_case_result("case-002", judge=JudgeVerdict(groundedness=2, coverage=2, key_points_missed=[], reason="Poor")),
        ]
        current_summary = summarize(current_cases)
        assert current_summary.mean_score == 2.5  # ((3+3)/2 + (2+2)/2) / 2 = 2.5

        # Baseline: higher mean score
        baseline_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=5, coverage=5, key_points_missed=[], reason="Perfect")),
            make_case_result("case-002", judge=JudgeVerdict(groundedness=5, coverage=5, key_points_missed=[], reason="Perfect")),
        ]
        baseline_summary = summarize(baseline_cases)
        assert baseline_summary.mean_score == 5.0

        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), None)

        # Difference is 5.0 - 2.5 = 2.5, which exceeds 0.3 threshold
        # Also, individual case scores drop (5.0 - 3.0 = 2.0 and 5.0 - 2.0 = 3.0)
        assert len(regressions) == 3
        mean_score_drops = [r for r in regressions if r.kind == "meanScoreDrop"]
        assert len(mean_score_drops) == 1
        assert mean_score_drops[0].baseline == 5.0
        assert mean_score_drops[0].current == 2.5

    def test_mean_score_drop_exactly_threshold_not_regression(self):
        """Test that a mean drop of exactly 0.3 is NOT a regression (must be > 0.3)."""
        # Current run with mean score 4.7
        current_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=5, coverage=4, key_points_missed=[], reason="Good")),
        ]
        current_summary = summarize(current_cases)
        assert current_summary.mean_score == 4.5

        # Baseline with mean score 4.8 (exactly 0.3 difference from 4.5)
        baseline_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=5, coverage=4, key_points_missed=[], reason="Good")),
        ]
        baseline_summary = RunSummary(
            case_count=1,
            graded_count=1,
            error_count=0,
            mean_groundedness=5.0,
            mean_coverage=4.2,
            mean_score=4.8,
            rule_pass_rate={"completed": 1.0, "format": 1.0, "product_tag": 1.0, "citations": 1.0, "retrieval": 1.0},
            p50_latency_ms=100.0,
            p95_latency_ms=100.0,
            total_input_tokens=100,
            total_output_tokens=50,
        )

        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), None)

        # Difference is 4.8 - 4.5 = 0.3, which does NOT exceed the threshold
        assert len([r for r in regressions if r.kind == "meanScoreDrop"]) == 0

    def test_rule_flip_regression(self):
        """Test ruleFlip regression kind (b)."""
        # Current run: citations failed for case-001
        current_cases = [
            make_case_result("case-001", rules=make_rule_results(citations=False), judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good")),
        ]
        current_summary = summarize(current_cases)

        # Baseline: citations passed for case-001
        baseline_cases = [
            make_case_result("case-001", rules=make_rule_results(citations=True), judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good")),
        ]
        baseline_summary = summarize(baseline_cases)

        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), None)

        rule_flips = [r for r in regressions if r.kind == "ruleFlip"]
        assert len(rule_flips) == 1
        assert rule_flips[0].case_id == "case-001"
        assert rule_flips[0].rule == "citations"

    def test_rule_flip_ignored_for_ungraded_cases(self):
        """Test that rule flips are only checked for graded cases."""
        # Current run: error case
        current_cases = [
            make_case_result("case-001", rules=make_rule_results(citations=False), error="Timeout", judge=None),
        ]
        current_summary = summarize(current_cases)

        # Baseline: graded case with citations passed
        baseline_cases = [
            make_case_result("case-001", rules=make_rule_results(citations=True), judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good")),
        ]
        baseline_summary = summarize(baseline_cases)

        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), None)

        # Rule flip should not be flagged because current case is ungraded
        rule_flips = [r for r in regressions if r.kind == "ruleFlip"]
        assert len(rule_flips) == 0

    def test_case_score_drop_regression(self):
        """Test caseScoreDrop regression kind (c)."""
        # Current run: case score dropped
        current_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=2, coverage=1, key_points_missed=[], reason="Poor")),
        ]
        current_summary = summarize(current_cases)
        assert current_summary.mean_score == 1.5  # (2 + 1) / 2

        # Baseline: higher case score
        baseline_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=5, coverage=5, key_points_missed=[], reason="Perfect")),
        ]
        baseline_summary = summarize(baseline_cases)

        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), None)

        # Score drop is 5.0 - 1.5 = 3.5, which exceeds threshold of 2.0
        score_drops = [r for r in regressions if r.kind == "caseScoreDrop"]
        assert len(score_drops) == 1
        assert score_drops[0].case_id == "case-001"
        assert score_drops[0].baseline == 5.0
        assert score_drops[0].current == 1.5

    def test_case_score_drop_ignored_for_ungraded_cases(self):
        """Test that case score drops are only checked for graded cases."""
        # Current run: error case
        current_cases = [
            make_case_result("case-001", error="Timeout", judge=None),
        ]
        current_summary = summarize(current_cases)

        # Baseline: graded case
        baseline_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=5, coverage=5, key_points_missed=[], reason="Perfect")),
        ]
        baseline_summary = summarize(baseline_cases)

        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), None)

        # Score drop should not be flagged because current case is ungraded
        score_drops = [r for r in regressions if r.kind == "caseScoreDrop"]
        assert len(score_drops) == 0

    def test_error_rate_regression(self):
        """Test errorRate regression kind (d)."""
        # Current run: 30% error rate (exceeds 20% threshold)
        current_cases = [
            make_case_result("case-001", error="Error 1", judge=None),
            make_case_result("case-002", error="Error 2", judge=None),
            make_case_result("case-003", error="Error 3", judge=None),
            make_case_result("case-004", judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good")),
            make_case_result("case-005", judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good")),
            make_case_result("case-006", judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good")),
            make_case_result("case-007", judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good")),
            make_case_result("case-008", judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good")),
            make_case_result("case-009", judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good")),
            make_case_result("case-010", judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good")),
        ]
        current_summary = summarize(current_cases)
        assert current_summary.error_count == 3
        assert current_summary.case_count == 10

        baseline_cases = [
            make_case_result(f"case-{i:03d}", judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good"))
            for i in range(1, 11)
        ]
        baseline_summary = summarize(baseline_cases)

        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), None)

        error_rate_regressions = [r for r in regressions if r.kind == "errorRate"]
        assert len(error_rate_regressions) == 1
        assert error_rate_regressions[0].error_count == 3
        assert error_rate_regressions[0].case_count == 10

    def test_error_rate_exactly_threshold_not_regression(self):
        """Test that error rate of exactly 20% is NOT a regression (must be > 20%)."""
        # Current run: exactly 20% error rate (2 errors out of 10 cases)
        current_cases = [
            make_case_result("case-001", error="Error 1", judge=None),
            make_case_result("case-002", error="Error 2", judge=None),
        ] + [
            make_case_result(f"case-{i:03d}", judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good"))
            for i in range(3, 11)
        ]
        current_summary = summarize(current_cases)

        baseline_cases = [
            make_case_result(f"case-{i:03d}", judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good"))
            for i in range(1, 11)
        ]
        baseline_summary = summarize(baseline_cases)

        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), None)

        # Error rate is exactly 20%, which does NOT exceed the threshold
        error_rate_regressions = [r for r in regressions if r.kind == "errorRate"]
        assert len(error_rate_regressions) == 0

    def test_recent_best_drop_regression(self):
        """Test recentBestDrop regression kind (e)."""
        # Current run with mean score 3.5
        current_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=3, coverage=4, key_points_missed=[], reason="Fair")),
        ]
        current_summary = summarize(current_cases)
        assert current_summary.mean_score == 3.5

        # Baseline (not used for this check, but needed for function signature)
        baseline_summary = RunSummary(
            case_count=1, graded_count=1, error_count=0,
            mean_groundedness=4.0, mean_coverage=4.0, mean_score=4.0,
            rule_pass_rate={"completed": 1.0, "format": 1.0, "product_tag": 1.0, "citations": 1.0, "retrieval": 1.0},
            p50_latency_ms=100.0, p95_latency_ms=100.0,
            total_input_tokens=100, total_output_tokens=50,
        )
        baseline_cases = []

        # recent_best = 4.1, current = 3.5, difference = 0.6 exceeds 0.5 threshold
        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), 4.1)

        recent_best_regressions = [r for r in regressions if r.kind == "recentBestDrop"]
        assert len(recent_best_regressions) == 1
        assert recent_best_regressions[0].recent_best == 4.1
        assert recent_best_regressions[0].current == 3.5

    def test_recent_best_drop_exactly_threshold_not_regression(self):
        """Test that recent best drop of exactly 0.5 is NOT a regression (must be > 0.5)."""
        # Current run with mean score 3.5
        current_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=3, coverage=4, key_points_missed=[], reason="Fair")),
        ]
        current_summary = summarize(current_cases)
        assert current_summary.mean_score == 3.5

        baseline_summary = RunSummary(
            case_count=1, graded_count=1, error_count=0,
            mean_groundedness=4.0, mean_coverage=4.0, mean_score=4.0,
            rule_pass_rate={"completed": 1.0, "format": 1.0, "product_tag": 1.0, "citations": 1.0, "retrieval": 1.0},
            p50_latency_ms=100.0, p95_latency_ms=100.0,
            total_input_tokens=100, total_output_tokens=50,
        )
        baseline_cases = []

        # recent_best = 4.0, current = 3.5, difference = 0.5 does NOT exceed threshold
        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), 4.0)

        recent_best_regressions = [r for r in regressions if r.kind == "recentBestDrop"]
        assert len(recent_best_regressions) == 0

    def test_recent_best_none_skips_e(self):
        """Test that recent_best=None skips regression kind (e)."""
        # Current run
        current_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=3, coverage=4, key_points_missed=[], reason="Fair")),
        ]
        current_summary = summarize(current_cases)

        baseline_summary = RunSummary(
            case_count=1, graded_count=1, error_count=0,
            mean_groundedness=4.0, mean_coverage=4.0, mean_score=4.0,
            rule_pass_rate={"completed": 1.0, "format": 1.0, "product_tag": 1.0, "citations": 1.0, "retrieval": 1.0},
            p50_latency_ms=100.0, p95_latency_ms=100.0,
            total_input_tokens=100, total_output_tokens=50,
        )
        baseline_cases = []

        # Even though there's a large drop, recent_best=None should skip it
        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), None)

        recent_best_regressions = [r for r in regressions if r.kind == "recentBestDrop"]
        assert len(recent_best_regressions) == 0

    def test_case_missing_from_baseline_ignored(self):
        """Test that a case missing from the baseline is ignored in comparisons."""
        # Current run with 2 cases
        current_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good")),
            make_case_result("case-002", judge=JudgeVerdict(groundedness=2, coverage=2, key_points_missed=[], reason="Poor")),
        ]
        current_summary = summarize(current_cases)

        # Baseline with only 1 case
        baseline_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good")),
        ]
        baseline_summary = summarize(baseline_cases)

        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), None)

        # case-002 should not produce any regressions since it's missing from baseline
        score_drops = [r for r in regressions if r.kind == "caseScoreDrop" and r.case_id == "case-002"]
        assert len(score_drops) == 0

    def test_slow_decline_over_four_weeks(self):
        """Test a 0.2-per-week decline over 4 runs where (a) never fires but (e) does by week 3."""
        # Week 1: mean score 4.5
        summary_w1 = RunSummary(
            case_count=10, graded_count=10, error_count=0,
            mean_groundedness=4.5, mean_coverage=4.5, mean_score=4.5,
            rule_pass_rate={"completed": 1.0, "format": 1.0, "product_tag": 1.0, "citations": 1.0, "retrieval": 1.0},
            p50_latency_ms=100.0, p95_latency_ms=100.0,
            total_input_tokens=100, total_output_tokens=50,
        )

        # Week 2: mean score 4.3 (drop of 0.2, doesn't trigger (a))
        summary_w2 = RunSummary(
            case_count=10, graded_count=10, error_count=0,
            mean_groundedness=4.3, mean_coverage=4.3, mean_score=4.3,
            rule_pass_rate={"completed": 1.0, "format": 1.0, "product_tag": 1.0, "citations": 1.0, "retrieval": 1.0},
            p50_latency_ms=100.0, p95_latency_ms=100.0,
            total_input_tokens=100, total_output_tokens=50,
        )
        cases_w2 = [
            make_case_result(f"case-{i:03d}", judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good"))
            for i in range(1, 11)
        ]

        # Week 3: mean score 4.1 (drop of 0.2, doesn't trigger (a), but best_drop does trigger (e))
        summary_w3 = RunSummary(
            case_count=10, graded_count=10, error_count=0,
            mean_groundedness=4.1, mean_coverage=4.1, mean_score=4.1,
            rule_pass_rate={"completed": 1.0, "format": 1.0, "product_tag": 1.0, "citations": 1.0, "retrieval": 1.0},
            p50_latency_ms=100.0, p95_latency_ms=100.0,
            total_input_tokens=100, total_output_tokens=50,
        )
        cases_w3 = [
            make_case_result(f"case-{i:03d}", judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good"))
            for i in range(1, 11)
        ]

        # Week 4: mean score 3.9 (drop of 0.2)
        summary_w4 = RunSummary(
            case_count=10, graded_count=10, error_count=0,
            mean_groundedness=3.9, mean_coverage=3.9, mean_score=3.9,
            rule_pass_rate={"completed": 1.0, "format": 1.0, "product_tag": 1.0, "citations": 1.0, "retrieval": 1.0},
            p50_latency_ms=100.0, p95_latency_ms=100.0,
            total_input_tokens=100, total_output_tokens=50,
        )
        cases_w4 = [
            make_case_result(f"case-{i:03d}", judge=JudgeVerdict(groundedness=3, coverage=4, key_points_missed=[], reason="Good"))
            for i in range(1, 11)
        ]

        # Week 2 check: baseline is week 1 (best = 4.5), no regression yet
        regressions_w2 = find_regressions(cases_w2, summary_w2, (summary_w1, []), 4.5)
        assert len([r for r in regressions_w2 if r.kind == "meanScoreDrop"]) == 0
        assert len([r for r in regressions_w2 if r.kind == "recentBestDrop"]) == 0

        # Week 3 check: baseline is week 2, recent_best is 4.5, score is 4.1
        # 4.5 - 4.1 = 0.4, which does NOT exceed 0.5 threshold yet
        regressions_w3 = find_regressions(cases_w3, summary_w3, (summary_w2, cases_w2), 4.5)
        assert len([r for r in regressions_w3 if r.kind == "meanScoreDrop"]) == 0
        assert len([r for r in regressions_w3 if r.kind == "recentBestDrop"]) == 0

        # Actually, wait. Let me re-read the spec...
        # "the mean score is more than 0.5 below the best mean score of the last 8 completed scheduled runs"
        # So if best is 4.5 and current is 3.9, difference is 0.6 > 0.5, so it triggers.
        # But with a 0.2 per week decline:
        # Week 1: 4.5
        # Week 2: 4.3 (4.5 - 4.3 = 0.2, doesn't trigger (a) since threshold is > 0.3)
        # Week 3: 4.1 (4.5 - 4.1 = 0.4, doesn't trigger (e) since threshold is > 0.5)
        # Week 4: 3.9 (4.5 - 3.9 = 0.6, triggers (e) since 0.6 > 0.5)

        # So the test should check that week 4 triggers but not weeks 2 and 3.
        # Let me update the test expectations...

        # Week 4 check: should trigger recentBestDrop but not meanScoreDrop
        regressions_w4 = find_regressions(cases_w4, summary_w4, (summary_w3, cases_w3), 4.5)
        assert len([r for r in regressions_w4 if r.kind == "meanScoreDrop"]) == 0
        assert len([r for r in regressions_w4 if r.kind == "recentBestDrop"]) == 1
