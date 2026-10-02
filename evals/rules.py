"""
evals/rules.py — Deterministic rule checks for eval cases.

Implements the five rules from spec.md §2 R3:
- completed: no error
- format: all tags present with non-empty summary and root cause
- productTag: parsed tag equals expectedProductTag
- citations: no unretrieved doc URLs
- retrieval: when expectedSources is set, at least one chunk from each source
"""

import re
from typing import Optional

import chat
from evals.models import EvalCase, RuleResults


def parse_product_tag(response: str) -> Optional[str]:
    """Extract and return the product tag from the response, or None."""
    match = re.search(r'<product_tag>(.*?)</product_tag>', response, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def evaluate_rules(
    case: EvalCase,
    response: str,
    chunks: Optional[list[dict]],
    error: Optional[str]
) -> RuleResults:
    """Evaluate all five deterministic rule checks.

    When error is not None, completed is False and all other rules are False.
    Otherwise, each rule is evaluated independently.

    Args:
        case: The test case with expected values
        response: The response text from the model
        chunks: Retrieved doc chunks with 'source' and 'url' keys
        error: Error string if the case failed, None otherwise

    Returns:
        RuleResults with boolean values for each rule
    """

    # Rule 1: completed - there is no error
    completed = error is None

    # If there's an error, short-circuit all other rules to False
    if error is not None:
        return RuleResults(
            completed=False,
            format=False,
            product_tag=False,
            citations=False,
            retrieval=False
        )

    # Rule 2: format - all tags present and summary/root_cause non-empty
    format_ok = _check_format(response)

    # Rule 3: productTag - parsed tag equals expectedProductTag
    parsed_tag = parse_product_tag(response)
    product_tag_ok = parsed_tag == case.expected_product_tag

    # Rule 4: citations - find_unretrieved_doc_urls is empty
    unretrieved = chat.find_unretrieved_doc_urls(response, chunks)
    citations_ok = len(unretrieved) == 0

    # Rule 5: retrieval - when expectedSources is set, at least one chunk from each source
    retrieval_ok = _check_retrieval(case, chunks)

    return RuleResults(
        completed=completed,
        format=format_ok,
        product_tag=product_tag_ok,
        citations=citations_ok,
        retrieval=retrieval_ok
    )


def _check_format(response: str) -> bool:
    """Check that all required tags are present and summary/root_cause are non-empty."""
    required_tags = ['product_tag', 'summary', 'root_cause', 'debug_steps', 'docs']

    # Check all tags are present
    for tag in required_tags:
        if re.search(rf'<{tag}>.*?</{tag}>', response, re.IGNORECASE | re.DOTALL) is None:
            return False

    # Check that summary and root_cause are non-empty
    summary_match = re.search(r'<summary>(.*?)</summary>', response, re.IGNORECASE | re.DOTALL)
    root_cause_match = re.search(r'<root_cause>(.*?)</root_cause>', response, re.IGNORECASE | re.DOTALL)

    summary_text = summary_match.group(1).strip() if summary_match else ""
    root_cause_text = root_cause_match.group(1).strip() if root_cause_match else ""

    return bool(summary_text and root_cause_text)


def _check_retrieval(case: EvalCase, chunks: Optional[list[dict]]) -> bool:
    """Check retrieval: when expectedSources is set, at least one chunk from each source."""
    # When expectedSources is unset, retrieval passes
    if case.expected_sources is None:
        return True

    # Extract sources from retrieved chunks
    retrieved_sources = set()
    for chunk in (chunks or []):
        if isinstance(chunk, dict) and "source" in chunk:
            retrieved_sources.add(chunk["source"])

    # Check that at least one chunk from each expected source is present
    return all(source in retrieved_sources for source in case.expected_sources)
