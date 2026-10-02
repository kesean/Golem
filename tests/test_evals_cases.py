"""
Tests for the evaluation cases schema and data.
"""

import json
import re
from pathlib import Path
from collections import Counter

import pytest
from pydantic import ValidationError

from evals.models import (
    CasesFile, EvalCase, JudgeVerdict, Regression,
    MeanScoreDrop, RuleFlip, CaseScoreDrop, ErrorRate, RecentBestDrop,
    EvalRunPayload, Run, RunSummary, RuleResults, CaseResult,
)


# Load the prompt.py to extract valid product tags
def get_valid_product_tags():
    """Extract valid product tags from prompt.py line 29."""
    prompt_file = Path(__file__).parent.parent / "prompt.py"
    with open(prompt_file) as f:
        content = f.read()

    # Match: "- <product_tag> must be exactly one of: ..."
    match = re.search(r"must be exactly one of:\s*(.+)", content)
    assert match, "Could not find product tag line in prompt.py"

    tags_str = match.group(1).strip()
    # Remove trailing period if present
    if tags_str.endswith('.'):
        tags_str = tags_str[:-1]

    # Split on comma and strip whitespace
    tags = [tag.strip() for tag in tags_str.split(',')]
    return tags


@pytest.fixture(scope="session")
def valid_tags():
    """Get the valid product tags from prompt.py."""
    return get_valid_product_tags()


@pytest.fixture(scope="session")
def cases_data():
    """Load the cases.json file."""
    cases_file = Path(__file__).parent.parent / "evals" / "cases.json"
    with open(cases_file) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def cases_file(cases_data):
    """Parse cases.json as CasesFile model."""
    return CasesFile(**cases_data)


def test_schema_loads(cases_file):
    """Test that evals/cases.json loads and validates against CasesFile schema."""
    assert cases_file is not None
    assert cases_file.version == 1
    assert len(cases_file.cases) > 0


def test_ids_are_unique(cases_file):
    """Test that all case IDs are unique."""
    ids = [case.id for case in cases_file.cases]
    assert len(ids) == len(set(ids)), "Duplicate case IDs found"


def test_ids_are_kebab_case(cases_file):
    """Test that all case IDs are in kebab-case."""
    kebab_pattern = re.compile(r"^[a-z0-9]+-[a-z0-9-]*[a-z0-9]$|^[a-z0-9]+$")
    for case in cases_file.cases:
        assert kebab_pattern.match(case.id), f"ID '{case.id}' is not kebab-case"


def test_category_minimums(cases_file):
    """Test that category minimums are met."""
    categories = Counter(case.category for case in cases_file.cases)

    assert categories['clerk-auth'] >= 10, \
        f"Expected ≥ 10 clerk-auth cases, got {categories['clerk-auth']}"
    assert categories['web-platform'] >= 8, \
        f"Expected ≥ 8 web-platform cases, got {categories['web-platform']}"
    assert categories['limits-config'] >= 4, \
        f"Expected ≥ 4 limits-config cases, got {categories['limits-config']}"
    assert categories['off-topic'] >= 3, \
        f"Expected ≥ 3 off-topic cases, got {categories['off-topic']}"
    assert categories['injection'] >= 3, \
        f"Expected ≥ 3 injection cases, got {categories['injection']}"


def test_total_case_count(cases_file):
    """Test that there are at least 30 cases."""
    assert len(cases_file.cases) >= 30, \
        f"Expected ≥ 30 cases, got {len(cases_file.cases)}"


def test_tags_match_prompt_list(cases_file, valid_tags):
    """Test that all expectedProductTag values are in the prompt.py list."""
    for case in cases_file.cases:
        assert case.expected_product_tag in valid_tags, \
            f"Tag '{case.expected_product_tag}' in case '{case.id}' is not in prompt.py list: {valid_tags}"


def test_off_topic_and_injection_expect_other_tag(cases_file):
    """Test that off-topic and injection cases expect 'Other' tag."""
    for case in cases_file.cases:
        if case.category in ('off-topic', 'injection'):
            assert case.expected_product_tag == 'Other', \
                f"Case '{case.id}' with category '{case.category}' should expect tag 'Other', got '{case.expected_product_tag}'"


def test_key_points_count(cases_file):
    """Test that each case has 2-4 key points."""
    for case in cases_file.cases:
        assert 2 <= len(case.key_points) <= 4, \
            f"Case '{case.id}' has {len(case.key_points)} key points, expected 2-4"


def test_key_points_not_empty(cases_file):
    """Test that each key point is a non-empty string."""
    for case in cases_file.cases:
        for i, point in enumerate(case.key_points):
            assert isinstance(point, str), \
                f"Case '{case.id}' key point {i} is not a string"
            assert len(point) > 0, \
                f"Case '{case.id}' key point {i} is empty"


def test_question_length(cases_file):
    """Test that questions are at most 2000 characters."""
    for case in cases_file.cases:
        assert len(case.question) <= 2000, \
            f"Case '{case.id}' question exceeds 2000 chars ({len(case.question)} chars)"


def test_question_not_empty(cases_file):
    """Test that questions are not empty."""
    for case in cases_file.cases:
        assert len(case.question) > 0, \
            f"Case '{case.id}' has empty question"


def test_expected_sources_valid(cases_file):
    """Test that expectedSources only contains 'clerk' or 'mdn'."""
    valid_sources = {'clerk', 'mdn'}
    for case in cases_file.cases:
        if case.expected_sources:
            for source in case.expected_sources:
                assert source in valid_sources, \
                    f"Case '{case.id}' has invalid source '{source}'"


def test_expected_sources_for_categories(cases_file):
    """Test that expectedSources are appropriately set."""
    for case in cases_file.cases:
        if case.category == 'clerk-auth':
            if case.expected_sources:
                assert 'clerk' in case.expected_sources, \
                    f"Case '{case.id}' with clerk-auth category should have 'clerk' source"
        elif case.category == 'web-platform':
            if case.expected_sources:
                assert 'mdn' in case.expected_sources, \
                    f"Case '{case.id}' with web-platform category should have 'mdn' source"


def test_prompt_tag_line_format(valid_tags):
    """Test that we can parse the tag line from prompt.py."""
    # This is validated by the fixture, but we double-check here
    assert len(valid_tags) == 12, \
        f"Expected 12 product tags, got {len(valid_tags)}"
    expected_tags = [
        'Authentication', 'Rate Limits', 'CORS', 'SDK', 'Networking', 'Database',
        'Configuration', 'Deployment', 'Performance', 'Streaming', 'Debugging', 'Other'
    ]
    assert set(valid_tags) == set(expected_tags), \
        f"Tags mismatch. Got {set(valid_tags)}, expected {set(expected_tags)}"


def test_expected_sources_required_for_categories(cases_file):
    """Test that clerk-auth and web-platform cases have expectedSources."""
    for case in cases_file.cases:
        if case.category == 'clerk-auth':
            assert case.expected_sources is not None, \
                f"Case '{case.id}' with clerk-auth category must have expectedSources"
            assert 'clerk' in case.expected_sources, \
                f"Case '{case.id}' with clerk-auth category must include 'clerk' source"
        elif case.category == 'web-platform':
            assert case.expected_sources is not None, \
                f"Case '{case.id}' with web-platform category must have expectedSources"
            assert 'mdn' in case.expected_sources, \
                f"Case '{case.id}' with web-platform category must include 'mdn' source"


def test_two_cases_fixture_loads():
    """Test that evals/fixtures/two_cases.json loads and validates."""
    fixtures_file = Path(__file__).parent.parent / "evals" / "fixtures" / "two_cases.json"
    with open(fixtures_file) as f:
        data = json.load(f)

    cases_file = CasesFile(**data)
    assert len(cases_file.cases) == 2, f"Expected 2 fixture cases, got {len(cases_file.cases)}"
    assert cases_file.version == 1


def test_alias_serialization_keys():
    """Test that models serialize to camelCase by default."""
    case = EvalCase(
        id="test-001",
        question="What is X?",
        expected_product_tag="Other",
        key_points=["point 1", "point 2"],
        category="off-topic",
    )

    # Serialize with aliases
    data = case.model_dump()

    # Check camelCase keys are present
    assert "expectedProductTag" in data, "expectedProductTag not in serialized dict"
    assert "keyPoints" in data, "keyPoints not in serialized dict"
    assert "expected_product_tag" not in data, "snake_case field in serialized dict"
    assert "key_points" not in data, "snake_case field in serialized dict"


def test_judge_verdict_rejects_invalid_scores():
    """Test that JudgeVerdict rejects scores outside 1-5 range."""
    # Valid verdict should work
    valid = JudgeVerdict(
        groundedness=3,
        coverage=4,
        key_points_missed=[],
        reason="Good response"
    )
    assert valid.groundedness == 3

    # Score of 0 should fail
    with pytest.raises(ValidationError):
        JudgeVerdict(
            groundedness=0,
            coverage=4,
            key_points_missed=[],
            reason="Good response"
        )

    # Score of 6 should fail
    with pytest.raises(ValidationError):
        JudgeVerdict(
            groundedness=6,
            coverage=4,
            key_points_missed=[],
            reason="Good response"
        )


def test_judge_verdict_rejects_empty_reason():
    """Test that JudgeVerdict rejects empty reason."""
    with pytest.raises(ValidationError):
        JudgeVerdict(
            groundedness=3,
            coverage=4,
            key_points_missed=[],
            reason=""
        )


def test_eval_case_rejects_oversized_question():
    """Test that EvalCase rejects questions over 2000 chars."""
    long_question = "x" * 2001

    with pytest.raises(ValidationError):
        EvalCase(
            id="test-001",
            question=long_question,
            expected_product_tag="Other",
            key_points=["p1", "p2"],
            category="off-topic",
        )


def test_eval_case_rejects_invalid_key_point_count():
    """Test that EvalCase rejects 1 or 5+ key points."""
    # 1 key point should fail
    with pytest.raises(ValidationError):
        EvalCase(
            id="test-001",
            question="What is X?",
            expected_product_tag="Other",
            key_points=["point1"],
            category="off-topic",
        )

    # 5 key points should fail
    with pytest.raises(ValidationError):
        EvalCase(
            id="test-001",
            question="What is X?",
            expected_product_tag="Other",
            key_points=["p1", "p2", "p3", "p4", "p5"],
            category="off-topic",
        )


def test_regression_round_trip_all_kinds():
    """Test that Regression discriminated union round-trips for all kinds through TypeAdapter."""
    from pydantic import TypeAdapter

    # Test with camelCase (as it will be serialized)
    test_cases = [
        {"kind": "meanScoreDrop", "baseline": 0.8, "current": 0.5},
        {"kind": "ruleFlip", "caseId": "test-001", "rule": "citations"},
        {"kind": "caseScoreDrop", "caseId": "test-001", "baseline": 4.0, "current": 2.0},
        {"kind": "errorRate", "errorCount": 5, "caseCount": 30},
        {"kind": "recentBestDrop", "recentBest": 4.2, "current": 3.9},
    ]

    adapter = TypeAdapter(Regression)
    for data in test_cases:
        # Parse via TypeAdapter (accepts both snake and camelCase due to populate_by_name)
        regression = adapter.validate_python(data)
        assert regression.kind == data["kind"], f"Kind mismatch for {data['kind']}"

        # Serialize and compare (will be in camelCase due to serialize_by_alias)
        serialized = adapter.dump_python(regression)
        assert serialized == data, f"Round-trip failed for {data['kind']}"


def test_eval_run_payload_from_camel_case_dict():
    """Test that EvalRunPayload can be built from camelCase JSON dict."""
    payload_dict = {
        "run": {
            "label": "manual",
            "gitSha": "abc123",
            "gitRef": "main",
            "appModel": "claude-sonnet-5",
            "judgeModel": "deepseek-flash",
            "casesVersion": 1,
            "startedAt": 1696000000000,
            "finishedAt": 1696000060000,
            "status": "completed",
            "summary": {
                "caseCount": 2,
                "gradedCount": 2,
                "errorCount": 0,
                "meanGroundedness": 4.0,
                "meanCoverage": 4.0,
                "meanScore": 4.0,
                "rulePassRate": {
                    "completed": 1.0,
                    "format": 1.0,
                    "productTag": 1.0,
                    "citations": 1.0,
                    "retrieval": 1.0,
                },
                "p50LatencyMs": 2500.0,
                "p95LatencyMs": 3000.0,
                "totalInputTokens": 1000,
                "totalOutputTokens": 500,
            },
            "regressions": [],
            "baselineRunId": None,
        },
        "results": [],
    }

    # Should parse camelCase dict
    payload = EvalRunPayload(**payload_dict)
    assert payload.run.git_sha == "abc123"
    assert payload.run.app_model == "claude-sonnet-5"
    assert payload.run.judge_model == "deepseek-flash"

    # Check serialization uses camelCase
    serialized = payload.model_dump()
    assert "gitSha" in serialized["run"], "gitSha not in serialized dict"
    assert "git_sha" not in serialized["run"], "snake_case in serialized dict"
