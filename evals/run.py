"""
evals/run.py — Main evaluation harness runner.

Orchestrates the full pipeline:
1. Load cases from JSON
2. Run each case through chat.stream_run with bounded concurrency
3. Apply rule checks and grading
4. Compute summary and detect regressions
5. Upload to Convex (optional)
6. Write report files
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import chat
from evals import convex_client, report
from evals.judge import judge_case
from evals.models import (
    CaseResult,
    CasesFile,
    EvalCase,
    EvalRunPayload,
    Run,
    RuleResults,
)
from evals.regression import find_regressions, summarize
from evals.rules import evaluate_rules, parse_product_tag

logger = logging.getLogger(__name__)


def main(
    label: str = "manual",
    cases_file: Optional[str] = None,
    out_dir: str = "eval-out",
    no_upload: bool = False,
    dry_judge: bool = False,
    concurrency: int = 3,
) -> int:
    """
    Run the evaluation harness.

    Args:
        label: 'manual' or 'scheduled'
        cases_file: Path to cases.json
        out_dir: Output directory for run.json and report.md
        no_upload: Skip uploading to Convex
        dry_judge: Use fixed verdict instead of calling judge
        concurrency: Max concurrent case runs

    Returns:
        0: clean run
        2: regressions found
        1: harness error
    """
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info(f"Starting eval run: label={label}, concurrency={concurrency}")

    # Load cases
    if not cases_file:
        cases_file = "evals/cases.json"

    try:
        with open(cases_file) as f:
            cases_data = json.load(f)
        cases_file_obj = CasesFile(**cases_data)
        cases = cases_file_obj.cases
    except Exception as e:
        logger.error(f"Failed to load cases: {e}")
        return 1

    logger.info(f"Loaded {len(cases)} cases from {cases_file}")

    # Create output directory
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Record start time
    started_at = int(time.time() * 1000)

    # Run cases with bounded concurrency
    results = _run_cases_concurrent(
        cases,
        concurrency=concurrency,
        dry_judge=dry_judge,
    )

    # Record finish time
    finished_at = int(time.time() * 1000)

    logger.info(f"Completed {len(results)} cases")

    # Compute summary
    summary = summarize(results)

    logger.info(
        f"Summary: mean_score={summary.mean_score:.2f}, "
        f"error_count={summary.error_count}, graded={summary.graded_count}"
    )

    # Check for ungraded runs (graded_count == 0)
    if summary.graded_count == 0:
        logger.error("No cases were graded (grader failure?). Marking run as errored.")
        status = "errored"
        exit_code = 1
    else:
        status = "completed"
        exit_code = 0

    # Fetch baseline
    baseline_info = convex_client.fetch_baseline()
    baseline_run_id = None

    if baseline_info:
        baseline_summary, baseline_results, recent_best = baseline_info
        baseline_run_id = _extract_baseline_run_id(baseline_info)
    else:
        baseline_summary = None
        baseline_results = None
        recent_best = None
        logger.info("No baseline available")

    # Detect regressions
    baseline = (baseline_summary, baseline_results) if baseline_summary else None
    regressions = find_regressions(results, summary, baseline, recent_best)

    if regressions:
        logger.warning(f"Detected {len(regressions)} regression(s)")
        exit_code = 2  # Override clean exit if regressions found

    # Get git info
    git_sha = os.getenv("GITHUB_SHA") or _git_rev_parse("HEAD")
    git_ref = os.getenv("GITHUB_REF_NAME") or _git_rev_parse("--abbrev-ref", "HEAD")

    logger.info(f"Git: SHA={git_sha}, REF={git_ref}")

    # Build payload
    run = Run(
        label=label,
        git_sha=git_sha,
        git_ref=git_ref,
        app_model=chat.MODEL,
        judge_model=os.getenv("JUDGE_MODEL", "deepseek-flash"),
        cases_version=cases_file_obj.version,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        summary=summary,
        regressions=regressions,
        baseline_run_id=baseline_run_id,
    )

    payload = EvalRunPayload(run=run, results=results)

    # Write run.json
    run_json_path = out_path / "run.json"
    with open(run_json_path, "w") as f:
        # Serialize with camelCase aliases
        payload_dict = payload.model_dump(by_alias=True, exclude_none=True)
        json.dump(payload_dict, f, indent=2)
    logger.info(f"Wrote {run_json_path}")

    # Upload to Convex (unless --no-upload)
    if not no_upload:
        run_id = convex_client.upload(payload)
        if run_id:
            # Update payload with runId and write again
            payload_dict = payload.model_dump(by_alias=True, exclude_none=True)
            payload_dict["run"]["runId"] = run_id
            with open(run_json_path, "w") as f:
                json.dump(payload_dict, f, indent=2)
            logger.info(f"Updated run.json with runId: {run_id}")
        else:
            logger.warning("Upload failed; run not sent to Convex")
            if status == "completed":
                # Upload failure does not change exit code for completed runs
                pass

    # Generate and write report
    report_text = report.generate_report(
        run=run,
        results=results,
        baseline=(baseline_summary, baseline_results) if baseline_summary else None,
    )

    report_path = out_path / "report.md"
    with open(report_path, "w") as f:
        f.write(report_text)
    logger.info(f"Wrote {report_path}")

    # Print report to stdout
    print("\n" + report_text)

    logger.info(f"Run complete. Exit code: {exit_code}")

    return exit_code


def _run_cases_concurrent(
    cases: list[EvalCase],
    concurrency: int,
    dry_judge: bool,
) -> list[CaseResult]:
    """
    Run cases with bounded concurrency.

    Each case calls chat.stream_run, applies rules, and optionally calls the judge.
    Exceptions are caught and recorded as errors.

    Returns:
        Results in the same order as cases.
    """
    results = [None] * len(cases)  # Preserve order

    def run_case(idx_case_tuple):
        idx, case = idx_case_tuple
        try:
            result = _run_single_case(case, dry_judge=dry_judge)
        except Exception as e:
            logger.exception(f"Unexpected error running case {case.id}: {e}")
            # Create an error result
            result = CaseResult(
                case_id=case.id,
                question=case.question,
                response="",
                product_tag=None,
                retrieved_urls=[],
                rules=RuleResults(
                    completed=False,
                    format=False,
                    product_tag=False,
                    citations=False,
                    retrieval=False,
                ),
                judge=None,
                latency_ms=0,
                input_tokens=0,
                output_tokens=0,
                error=str(e),
            )
        results[idx] = result

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        # Submit all cases
        futures = []
        for idx, case in enumerate(cases):
            future = executor.submit(run_case, (idx, case))
            futures.append(future)

        # Wait for all to complete (but they update results[idx] directly)
        for future in futures:
            future.result()

    return results


def _run_single_case(case: EvalCase, dry_judge: bool) -> CaseResult:
    """
    Run a single case: stream_run, rules, judge.

    Returns:
        CaseResult with all fields populated.
    """
    # Determine if we should use fake pipeline
    use_fake = os.getenv("EVAL_FAKE_PIPELINE") == "1"

    if use_fake:
        # Deterministic stub answer
        response_text = _fake_pipeline_response(case)
        input_tokens = 100
        output_tokens = 50
        latency_ms = 500
        chunks = [
            {
                "source": source,
                "url": f"https://example.com/{source}",
                "text": f"Stub chunk from {source}",
            }
            for source in (case.expected_sources or ["clerk"])
        ]
        error = None
    else:
        # Real pipeline: call chat.stream_run
        try:
            response_text = ""
            input_tokens = 0
            output_tokens = 0
            latency_ms = 0
            chunks = []

            for event in chat.stream_run(case.question, []):
                if event["type"] == "delta":
                    response_text += event["text"]
                elif event["type"] == "done":
                    input_tokens = event["input_tokens"]
                    output_tokens = event["output_tokens"]
                    latency_ms = event["latency_ms"]
                    chunks = event.get("chunks", [])

            error = None
        except Exception as e:
            try:
                logger.warning(f"Case {case.id} failed: {e}")
            except:
                pass
            response_text = ""
            input_tokens = 0
            output_tokens = 0
            latency_ms = 0
            chunks = []
            try:
                error = str(e)
            except:
                error = "Unknown error"

    # Evaluate rules
    rules = evaluate_rules(case, response_text, chunks, error)

    # Parse product tag
    product_tag = parse_product_tag(response_text) if response_text else None

    # Judge (only if no error)
    judge = None
    judge_error = None

    if error is None:
        if dry_judge:
            # Fixed verdict for dry run
            judge = {
                "groundedness": 3,
                "coverage": 3,
                "key_points_missed": [],
                "reason": "Dry judge: fixed verdict.",
            }
        else:
            # Call the grader
            judge, judge_error = judge_case(case, response_text, chunks or [])

    # Extract retrieved URLs from chunks
    retrieved_urls = [c.get("url", "") for c in (chunks or []) if c.get("url")]

    return CaseResult(
        case_id=case.id,
        question=case.question,
        response=response_text,
        product_tag=product_tag,
        retrieved_urls=retrieved_urls,
        rules=rules,
        judge=judge,
        judge_error=judge_error,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        error=error,
    )


def _fake_pipeline_response(case: EvalCase) -> str:
    """Generate a deterministic stub response for offline mode."""
    tag = case.expected_product_tag
    sources_text = ""
    if case.expected_sources:
        sources_text = "\n".join(
            f"<docs>https://example.com/{source}</docs>" for source in case.expected_sources
        )
    else:
        sources_text = "<docs>https://example.com/default</docs>"

    return f"""<product_tag>{tag}</product_tag>
<summary>Stub answer for {tag}</summary>
<root_cause>This is a stub response</root_cause>
<debug_steps>Not applicable in offline mode</debug_steps>
{sources_text}"""


def _extract_baseline_run_id(baseline_info: tuple) -> Optional[str]:
    """Extract the baseline run ID from the fetch_baseline result."""
    # The baseline_info is (summary, results, recent_best)
    # We need to extract the run ID from the baseline results' _id field
    # But that's not directly accessible from the results list.
    # The spec says: "The baseline run's `_id` is the baselineRunId for the new payload."
    # Since we get results from the Convex fetch_baseline endpoint, the runId should be
    # carried through the response somehow. For now, return None and let the baseline
    # be resolved by case ID matching in regression detection.
    # TODO: When convex_client.fetch_baseline is updated to include the run ID,
    # extract it here.
    return None


def _git_rev_parse(*args) -> str:
    """Run git rev-parse and return the output."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", *args],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception as e:
        logger.warning(f"git rev-parse {args} failed: {e}")
        return "unknown"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run evaluation harness")
    parser.add_argument(
        "--label",
        default="manual",
        choices=["manual", "scheduled"],
        help="Run label",
    )
    parser.add_argument(
        "--cases",
        dest="cases_file",
        help="Path to cases.json",
    )
    parser.add_argument(
        "--out",
        dest="out_dir",
        default="eval-out",
        help="Output directory",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Skip uploading to Convex",
    )
    parser.add_argument(
        "--dry-judge",
        action="store_true",
        help="Use fixed judge verdict (no DeepSeek call)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Max concurrent case runs",
    )

    args = parser.parse_args()

    exit_code = main(
        label=args.label,
        cases_file=args.cases_file,
        out_dir=args.out_dir,
        no_upload=args.no_upload,
        dry_judge=args.dry_judge,
        concurrency=args.concurrency,
    )

    sys.exit(exit_code)
