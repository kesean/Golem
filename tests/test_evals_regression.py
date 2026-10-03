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
        if error is not None:
            rules = make_rule_results(completed=False)
        else:
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
        assert summary.mean_score == 3.5
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
        assert summary.mean_groundedness == 4.0
        assert abs(summary.mean_coverage - 3.666666666666667) < 0.0001
        mean_score_expected = ((5 + 5) / 2 + (3 + 2) / 2 + (4 + 4) / 2) / 3
        assert abs(summary.mean_score - mean_score_expected) < 0.0001
        assert summary.total_input_tokens == 300
        assert summary.total_output_tokens == 150
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
        assert summary.graded_count == 2
        assert summary.error_count == 1
        assert summary.mean_groundedness == 4.5
        assert summary.mean_coverage == 4.0
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
        cases = [
            make_case_result(f"case-{i:03d}", judge=JudgeVerdict(groundedness=4, coverage=3, key_points_missed=[], reason="Good"), latency_ms=(i + 1) * 100)
            for i in range(10)
        ]

        summary = summarize(cases)

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

    def test_baseline_none_with_recent_best_returns_empty(self):
        """Test that baseline=None with recent_best=4.5 returns [] (baseline required for all regressions)."""
        cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=2, coverage=2, key_points_missed=[], reason="Poor"))
        ]
        summary = summarize(cases)

        regressions = find_regressions(cases, summary, None, 4.5)

        assert regressions == []

    def test_mean_score_drop_regression(self):
        """Test meanScoreDrop regression kind (a)."""
        current_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=3, coverage=3, key_points_missed=[], reason="Fair")),
            make_case_result("case-002", judge=JudgeVerdict(groundedness=2, coverage=2, key_points_missed=[], reason="Poor")),
        ]
        current_summary = summarize(current_cases)
        assert current_summary.mean_score == 2.5

        baseline_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=5, coverage=5, key_points_missed=[], reason="Perfect")),
            make_case_result("case-002", judge=JudgeVerdict(groundedness=5, coverage=5, key_points_missed=[], reason="Perfect")),
        ]
        baseline_summary = summarize(baseline_cases)
        assert baseline_summary.mean_score == 5.0

        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), None)

        assert len(regressions) == 3
        mean_score_drops = [r for r in regressions if r.kind == "meanScoreDrop"]
        assert len(mean_score_drops) == 1
        assert mean_score_drops[0].baseline == 5.0
        assert mean_score_drops[0].current == 2.5

    @pytest.mark.parametrize("baseline_g,baseline_c,current_g,current_c,should_flag", [
        (4, 3, 4, 3, False),
        (5, 4, 5, 4, False),
        (3, 3, 3, 3, False),
        (5, 4, 3, 3, True),
        (5, 4, 3, 3, True),
    ])
    def test_mean_score_drop_boundary_cases(self, baseline_g, baseline_c, current_g, current_c, should_flag):
        """Test meanScoreDrop boundary: no drop is not flagged, large drop is flagged."""
        baseline_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=baseline_g, coverage=baseline_c, key_points_missed=[], reason="B"))
        ]
        baseline_summary = summarize(baseline_cases)

        current_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=current_g, coverage=current_c, key_points_missed=[], reason="C"))
        ]
        current_summary = summarize(current_cases)

        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), None)

        mean_score_drops = [r for r in regressions if r.kind == "meanScoreDrop"]
        if should_flag:
            assert len(mean_score_drops) == 1
        else:
            assert len(mean_score_drops) == 0

    def test_rule_flip_regression(self):
        """Test ruleFlip regression kind (b)."""
        current_cases = [
            make_case_result("case-001", rules=make_rule_results(citations=False), judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good")),
        ]
        current_summary = summarize(current_cases)

        baseline_cases = [
            make_case_result("case-001", rules=make_rule_results(citations=True), judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good")),
        ]
        baseline_summary = summarize(baseline_cases)

        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), None)

        rule_flips = [r for r in regressions if r.kind == "ruleFlip"]
        assert len(rule_flips) == 1
        assert rule_flips[0].case_id == "case-001"
        assert rule_flips[0].rule == "citations"

    def test_rule_flip_on_errored_case(self):
        """Test that an errored case where completed passed in baseline produces a ruleFlip (b)."""
        current_cases = [
            make_case_result("case-001", rules=make_rule_results(completed=False), error="Timeout", judge=None),
        ]
        current_summary = summarize(current_cases)

        baseline_cases = [
            make_case_result("case-001", rules=make_rule_results(completed=True), judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good")),
        ]
        baseline_summary = summarize(baseline_cases)

        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), None)

        rule_flips = [r for r in regressions if r.kind == "ruleFlip" and r.rule == "completed"]
        assert len(rule_flips) == 1
        assert rule_flips[0].case_id == "case-001"

    def test_case_score_drop_regression(self):
        """Test caseScoreDrop regression kind (c)."""
        current_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=2, coverage=1, key_points_missed=[], reason="Poor")),
        ]
        current_summary = summarize(current_cases)
        assert current_summary.mean_score == 1.5

        baseline_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=5, coverage=5, key_points_missed=[], reason="Perfect")),
        ]
        baseline_summary = summarize(baseline_cases)

        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), None)

        score_drops = [r for r in regressions if r.kind == "caseScoreDrop"]
        assert len(score_drops) == 1
        assert score_drops[0].case_id == "case-001"
        assert score_drops[0].baseline == 5.0
        assert score_drops[0].current == 1.5

    def test_case_score_drop_ignored_for_ungraded_cases(self):
        """Test that case score drops are only checked for graded cases."""
        current_cases = [
            make_case_result("case-001", error="Timeout", judge=None),
        ]
        current_summary = summarize(current_cases)

        baseline_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=5, coverage=5, key_points_missed=[], reason="Perfect")),
        ]
        baseline_summary = summarize(baseline_cases)

        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), None)

        score_drops = [r for r in regressions if r.kind == "caseScoreDrop"]
        assert len(score_drops) == 0

    def test_case_score_drop_boundary_cases(self):
        """Test caseScoreDrop boundary: exactly 2.0 drop is flagged, 1.5 is not."""
        baseline_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=5, coverage=5, key_points_missed=[], reason="Perfect")),
            make_case_result("case-002", judge=JudgeVerdict(groundedness=5, coverage=5, key_points_missed=[], reason="Perfect")),
        ]
        baseline_summary = summarize(baseline_cases)

        current_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=3, coverage=3, key_points_missed=[], reason="Poor")),
            make_case_result("case-002", judge=JudgeVerdict(groundedness=3, coverage=4, key_points_missed=[], reason="Fair")),
        ]
        current_summary = summarize(current_cases)

        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), None)

        score_drops = [r for r in regressions if r.kind == "caseScoreDrop"]
        assert len(score_drops) == 1
        assert score_drops[0].case_id == "case-001"

    def test_error_rate_regression(self):
        """Test errorRate regression kind (d)."""
        current_cases = [
            make_case_result("case-001", error="Error 1", judge=None),
            make_case_result("case-002", error="Error 2", judge=None),
            make_case_result("case-003", error="Error 3", judge=None),
        ] + [
            make_case_result(f"case-{i:03d}", judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good"))
            for i in range(4, 11)
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
        """Test that error rate of exactly 20% is NOT a regression."""
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

        error_rate_regressions = [r for r in regressions if r.kind == "errorRate"]
        assert len(error_rate_regressions) == 0

    def test_recent_best_drop_regression(self):
        """Test recentBestDrop regression kind (e)."""
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

        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), 4.1)

        recent_best_regressions = [r for r in regressions if r.kind == "recentBestDrop"]
        assert len(recent_best_regressions) == 1
        assert recent_best_regressions[0].recent_best == 4.1
        assert recent_best_regressions[0].current == 3.5

    @pytest.mark.parametrize("recent_best,baseline_g,current_g,should_flag", [
        (4.0, 4, 4, False),
        (4.4, 5, 4, False),
        (4.5, 5, 3, True),
    ])
    def test_recent_best_drop_boundary_cases(self, recent_best, baseline_g, current_g, should_flag):
        """Test recentBestDrop boundary: no drop is not flagged, large drop is flagged."""
        current_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=current_g, coverage=4, key_points_missed=[], reason="C"))
        ]
        current_summary = summarize(current_cases)

        baseline_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=baseline_g, coverage=4, key_points_missed=[], reason="B"))
        ]
        baseline_summary = summarize(baseline_cases)

        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), recent_best)

        recent_best_regressions = [r for r in regressions if r.kind == "recentBestDrop"]
        if should_flag:
            assert len(recent_best_regressions) == 1
        else:
            assert len(recent_best_regressions) == 0

    def test_recent_best_none_skips_e(self):
        """Test that recent_best=None skips regression kind (e)."""
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

        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), None)

        recent_best_regressions = [r for r in regressions if r.kind == "recentBestDrop"]
        assert len(recent_best_regressions) == 0

    def test_case_missing_from_baseline_ignored(self):
        """Test that a case missing from the baseline is ignored in comparisons."""
        current_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good")),
            make_case_result("case-002", judge=JudgeVerdict(groundedness=2, coverage=2, key_points_missed=[], reason="Poor")),
        ]
        current_summary = summarize(current_cases)

        baseline_cases = [
            make_case_result("case-001", judge=JudgeVerdict(groundedness=4, coverage=4, key_points_missed=[], reason="Good")),
        ]
        baseline_summary = summarize(baseline_cases)

        regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), None)

        score_drops = [r for r in regressions if r.kind == "caseScoreDrop" and r.case_id == "case-002"]
        assert len(score_drops) == 0

    def test_slow_decline_over_four_weeks(self):
        """Test 4 weeks (0-3) with declining means: (a) never fires, (e) fires at week 3."""
        summaries = []
        case_lists = []

        week_0_cases = [
            make_case_result(f"case-{i:03d}", judge=JudgeVerdict(groundedness=5, coverage=4, key_points_missed=[], reason="G"))
            for i in range(1, 11)
        ]
        summaries.append(summarize(week_0_cases))
        case_lists.append(week_0_cases)

        week_1_cases = [
            make_case_result(f"case-{i:03d}", judge=JudgeVerdict(groundedness=5, coverage=4, key_points_missed=[], reason="G") if i <= 8 else JudgeVerdict(groundedness=4, coverage=3, key_points_missed=[], reason="G"))
            for i in range(1, 11)
        ]
        summaries.append(summarize(week_1_cases))
        case_lists.append(week_1_cases)

        week_2_cases = [
            make_case_result(f"case-{i:03d}", judge=JudgeVerdict(groundedness=5, coverage=4, key_points_missed=[], reason="G") if i <= 6 else JudgeVerdict(groundedness=4, coverage=3, key_points_missed=[], reason="G"))
            for i in range(1, 11)
        ]
        summaries.append(summarize(week_2_cases))
        case_lists.append(week_2_cases)

        week_3_cases = [
            make_case_result(f"case-{i:03d}", judge=JudgeVerdict(groundedness=5, coverage=4, key_points_missed=[], reason="G") if i <= 4 else JudgeVerdict(groundedness=4, coverage=3, key_points_missed=[], reason="G"))
            for i in range(1, 11)
        ]
        summaries.append(summarize(week_3_cases))
        case_lists.append(week_3_cases)

        for week_idx in range(1, 4):
            baseline_summary = summaries[week_idx - 1]
            baseline_cases = case_lists[week_idx - 1]
            current_summary = summaries[week_idx]
            current_cases = case_lists[week_idx]

            recent_best = max(s.mean_score for s in summaries[:week_idx])

            regressions = find_regressions(current_cases, current_summary, (baseline_summary, baseline_cases), recent_best)

            mean_score_drops = [r for r in regressions if r.kind == "meanScoreDrop"]
            assert len(mean_score_drops) == 0, f"Week {week_idx}: (a) should never fire"

            if week_idx < 3:
                recent_best_drops = [r for r in regressions if r.kind == "recentBestDrop"]
                assert len(recent_best_drops) == 0, f"Week {week_idx}: (e) should not fire; recent_best={recent_best:.2f}, current={current_summary.mean_score:.2f}"
            else:
                recent_best_drops = [r for r in regressions if r.kind == "recentBestDrop"]
                assert len(recent_best_drops) == 1, f"Week {week_idx}: (e) should fire; recent_best={recent_best:.2f}, current={current_summary.mean_score:.2f}"
