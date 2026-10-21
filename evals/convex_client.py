"""
Convex client for fetching baseline and uploading eval runs.

Provides:
- fetch_baseline() -> (RunSummary, list[CaseResult], recent_best, baseline_run_id) | None
- upload(payload: EvalRunPayload) -> runId
"""

import logging
import os
from typing import Optional

import httpx
from evals.models import EvalRunPayload, RunSummary, CaseResult, RulePassRate

logger = logging.getLogger(__name__)


def fetch_baseline() -> Optional[tuple[RunSummary, list[CaseResult], Optional[float], Optional[str]]]:
    """
    Fetch the latest scheduled baseline run from Convex.

    Returns:
        (baseline_summary, baseline_results, recent_best_mean_score, baseline_run_id) or None if no baseline.
        baseline_run_id is the Convex doc's _id (used for baselineRunId in new run).

    Logs a warning and returns None if fetch fails or endpoint is not configured.
    """
    convex_url = (os.getenv("CONVEX_SITE_URL") or "").rstrip("/")
    secret = os.getenv("EVAL_INGEST_SECRET")

    if not convex_url or not secret:
        logger.warning("CONVEX_SITE_URL or EVAL_INGEST_SECRET not set; skipping baseline fetch")
        return None

    endpoint = f"{convex_url}/evals/baseline"
    headers = {
        "Authorization": f"Bearer {secret}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client() as client:
            response = client.get(endpoint, headers=headers, timeout=30)

            if response.status_code == 401:
                logger.warning("Baseline fetch: 401 Unauthorized (invalid credentials)")
                return None

            if response.status_code == 404:
                logger.warning("Baseline fetch: 404 Not Found (endpoint not available)")
                return None

            if response.status_code >= 400:
                logger.warning(f"Baseline fetch failed: HTTP {response.status_code}")
                return None

            data = response.json()

            # Response is null when there is no baseline
            if data is None:
                logger.info("No baseline available (no completed scheduled runs yet)")
                return None

            # Parse the response: { run, results, recentBestMeanScore }
            run = data.get("run")
            results = data.get("results", [])
            recent_best = data.get("recentBestMeanScore")

            if not run:
                logger.warning("Baseline response missing run field")
                return None

            # Extract baseline run ID (_id is the Convex doc ID)
            baseline_run_id = run.get("_id")

            # Convex system fields (_id, _creationTime) are ignored when deserializing
            baseline_summary = _deserialize_run_summary(run.get("summary", {}))
            baseline_results = [_deserialize_case_result(r) for r in results]

            logger.info(
                f"Fetched baseline: {len(baseline_results)} results, "
                f"mean score {baseline_summary.mean_score:.2f}"
            )
            return baseline_summary, baseline_results, recent_best, baseline_run_id

    except Exception as e:
        logger.warning(f"Baseline fetch failed: {e}")
        return None


def upload(payload: EvalRunPayload) -> Optional[str]:
    """
    Upload an eval run to Convex.

    Args:
        payload: EvalRunPayload with run and results

    Returns:
        runId string on success, or None on failure.

    Logs an error if the upload fails, or a warning if the endpoint is not configured; returns None in both cases.
    """
    convex_url = (os.getenv("CONVEX_SITE_URL") or "").rstrip("/")
    secret = os.getenv("EVAL_INGEST_SECRET")

    if not convex_url or not secret:
        logger.warning("CONVEX_SITE_URL or EVAL_INGEST_SECRET not set; skipping upload")
        return None

    endpoint = f"{convex_url}/evals/runs"
    headers = {
        "Authorization": f"Bearer {secret}",
        "Content-Type": "application/json",
    }

    try:
        # Serialize payload with camelCase aliases
        payload_dict = payload.model_dump(by_alias=True, exclude_none=True)

        with httpx.Client() as client:
            response = client.post(endpoint, json=payload_dict, headers=headers, timeout=30)

            if response.status_code == 401:
                logger.error("Upload: 401 Unauthorized (invalid bearer token)")
                return None

            if response.status_code >= 400:
                error_detail = response.text
                logger.error(f"Upload failed: HTTP {response.status_code}: {error_detail}")
                return None

            data = response.json()
            run_id = data.get("runId")

            if not run_id:
                logger.error("Upload response missing runId")
                return None

            logger.info(f"Uploaded run: {run_id}")
            return run_id

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return None


def _deserialize_run_summary(data: dict) -> RunSummary:
    """Deserialize a run summary from Convex JSON (camelCase to snake_case)."""
    # Convex returns camelCase; pydantic model expects snake_case
    rule_pass_rate_data = data.get("rulePassRate", {})
    # Convert camelCase rulePassRate dict to RulePassRate model
    rule_pass_rate = RulePassRate(
        completed=float(rule_pass_rate_data.get("completed", 0.0)),
        format=float(rule_pass_rate_data.get("format", 0.0)),
        product_tag=float(rule_pass_rate_data.get("productTag", 0.0)),
        citations=float(rule_pass_rate_data.get("citations", 0.0)),
        retrieval=float(rule_pass_rate_data.get("retrieval", 0.0)),
    )

    return RunSummary(
        case_count=int(data.get("caseCount", 0)),
        graded_count=int(data.get("gradedCount", 0)),
        error_count=int(data.get("errorCount", 0)),
        mean_groundedness=float(data.get("meanGroundedness", 0.0)),
        mean_coverage=float(data.get("meanCoverage", 0.0)),
        mean_score=float(data.get("meanScore", 0.0)),
        rule_pass_rate=rule_pass_rate,
        p50_latency_ms=float(data.get("p50LatencyMs", 0.0)),
        p95_latency_ms=float(data.get("p95LatencyMs", 0.0)),
        total_input_tokens=int(data.get("totalInputTokens", 0)),
        total_output_tokens=int(data.get("totalOutputTokens", 0)),
    )


def _deserialize_case_result(data: dict) -> CaseResult:
    """Deserialize a case result from Convex JSON."""
    # Convex returns camelCase; pydantic model expects snake_case
    judge_data = data.get("judge")
    judge = None
    if judge_data:
        judge = {
            "groundedness": judge_data.get("groundedness"),
            "coverage": judge_data.get("coverage"),
            "key_points_missed": judge_data.get("keyPointsMissed", []),
            "reason": judge_data.get("reason", ""),
        }

    rules_data = data.get("rules", {})
    rules = {
        "completed": rules_data.get("completed", False),
        "format": rules_data.get("format", False),
        "product_tag": rules_data.get("productTag", False),
        "citations": rules_data.get("citations", False),
        "retrieval": rules_data.get("retrieval", False),
    }

    return CaseResult(
        case_id=data.get("caseId", ""),
        question=data.get("question", ""),
        response=data.get("response", ""),
        product_tag=data.get("productTag"),
        retrieved_urls=data.get("retrievedUrls", []),
        rules=rules,
        judge=judge,
        judge_error=data.get("judgeError"),
        latency_ms=int(data.get("latencyMs", 0)),
        input_tokens=int(data.get("inputTokens", 0)),
        output_tokens=int(data.get("outputTokens", 0)),
        error=data.get("error"),
    )
