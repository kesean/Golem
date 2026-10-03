"""
Contract test: the Python EvalRunPayload must serialize to exactly the JSON the
Convex ingest endpoint accepts (frontend/convex/evals.harness.test.ts POSTs the
same fixture).
"""

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from evals.models import (
    CaseResult, EvalRunPayload, JudgeVerdict, Regression, Run, RuleResults,
    CaseScoreDrop, ErrorRate, MeanScoreDrop, RecentBestDrop, RuleFlip,
)
from evals.regression import summarize

FIXTURE = Path(__file__).parent / "fixtures" / "eval_run_payload.json"


def _result(case_id, *, judge=None, error=None, product_tag="Authentication", **rules):
    r = dict(completed=True, format=True, product_tag=True, citations=True, retrieval=True)
    r.update(rules)
    return CaseResult(
        case_id=case_id, question=f"Q {case_id}", response="A",
        product_tag=product_tag, retrieved_urls=["https://clerk.com/docs"],
        rules=RuleResults(**r), judge=judge, latency_ms=100 + len(case_id),
        input_tokens=10, output_tokens=5, error=error,
    )


def build_payload() -> EvalRunPayload:
    verdict = JudgeVerdict(groundedness=4, coverage=3, key_points_missed=["x"], reason="ok")
    results = [
        _result("case-a", judge=verdict),
        _result("case-b", judge=None, product_tag=None, completed=False, format=False,
                citations=False, retrieval=False),
        _result("case-c", error="Timeout", completed=False, format=False,
                citations=False, retrieval=False, product_tag=None),
    ]
    summary = summarize(results)
    regressions = [
        MeanScoreDrop(kind="meanScoreDrop", baseline=4.0, current=3.5),
        RuleFlip(kind="ruleFlip", case_id="case-a", rule="productTag"),
        CaseScoreDrop(kind="caseScoreDrop", case_id="case-a", baseline=4.5, current=2.5),
        ErrorRate(kind="errorRate", error_count=1, case_count=3),
        RecentBestDrop(kind="recentBestDrop", recent_best=4.5, current=3.5),
    ]
    run = Run(
        label="manual", git_sha="abc123", git_ref="refs/heads/main",
        app_model="claude-sonnet-5", judge_model="deepseek-flash", cases_version=1,
        started_at=1700000000000, finished_at=1700000001000, status="completed",
        summary=summary, regressions=regressions, baseline_run_id=None,
    )
    return EvalRunPayload(run=run, results=results)


def test_payload_matches_committed_fixture():
    dumped = build_payload().model_dump(by_alias=True, mode="json")
    assert dumped == json.loads(FIXTURE.read_text())


def test_fixture_covers_all_regression_kinds_and_nulls():
    data = json.loads(FIXTURE.read_text())
    kinds = {r["kind"] for r in data["run"]["regressions"]}
    assert kinds == {"meanScoreDrop", "ruleFlip", "caseScoreDrop", "errorRate", "recentBestDrop"}
    assert data["run"]["baselineRunId"] is None
    assert any(r["judge"] is None for r in data["results"])
    assert any(r["productTag"] is None for r in data["results"])
    assert any(r["error"] is not None for r in data["results"])
    assert "productTag" in data["run"]["summary"]["rulePassRate"]


def test_unknown_regression_kind_rejected():
    with pytest.raises(ValidationError):
        TypeAdapter(Regression).validate_python({"kind": "bogus", "baseline": 1.0, "current": 0.5})


def test_unknown_rule_name_rejected():
    with pytest.raises(ValidationError):
        RuleFlip(kind="ruleFlip", case_id="c", rule="product_tag")
