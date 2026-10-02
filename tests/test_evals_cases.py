"""
Tests for the evaluation cases schema and data.
"""

import json
import re
from pathlib import Path
from collections import Counter

import pytest

from evals.models import CasesFile, EvalCase


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
