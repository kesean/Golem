"""
Pydantic models for the eval harness, matching spec §4.1.
"""

from typing import Annotated, Literal, Optional, Union
from pydantic import BaseModel, Field, ConfigDict, conlist, constr
from pydantic.alias_generators import to_camel

# Literal types
ProductTag = Literal[
    'Authentication',
    'Rate Limits',
    'CORS',
    'SDK',
    'Networking',
    'Database',
    'Configuration',
    'Deployment',
    'Performance',
    'Streaming',
    'Debugging',
    'Other',
]

DocSource = Literal['clerk', 'mdn']

EvalCategory = Literal[
    'clerk-auth',
    'web-platform',
    'limits-config',
    'off-topic',
    'injection',
]


class BaseEvalModel(BaseModel):
    """Base model with camelCase alias configuration."""
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class EvalCase(BaseEvalModel):
    """A test case for evaluation."""
    id: str
    question: constr(max_length=2000)  # type: ignore
    expected_product_tag: ProductTag
    key_points: Annotated[list[str], Field(min_length=2, max_length=4)]
    expected_sources: Optional[list[DocSource]] = None
    category: EvalCategory


class RuleResults(BaseEvalModel):
    """Results of deterministic rule checks."""
    completed: bool
    format: bool
    product_tag: bool
    citations: bool
    retrieval: bool


class JudgeVerdict(BaseEvalModel):
    """LLM grader output."""
    groundedness: Literal[1, 2, 3, 4, 5]
    coverage: Literal[1, 2, 3, 4, 5]
    key_points_missed: list[str]
    reason: constr(min_length=1)  # type: ignore


class CaseResult(BaseEvalModel):
    """Result of running a single evaluation case."""
    case_id: str
    question: str
    response: str
    product_tag: Optional[str] = None
    retrieved_urls: list[str]
    rules: RuleResults
    judge: Optional[JudgeVerdict] = None
    judge_error: Optional[str] = None
    latency_ms: int
    input_tokens: int
    output_tokens: int
    error: Optional[str] = None


class RunSummary(BaseEvalModel):
    """Summary statistics for an eval run."""
    case_count: int
    graded_count: int
    error_count: int
    mean_groundedness: float
    mean_coverage: float
    mean_score: float
    rule_pass_rate: dict[str, float]
    p50_latency_ms: float
    p95_latency_ms: float
    total_input_tokens: int
    total_output_tokens: int


# Discriminated union for Regression
class MeanScoreDrop(BaseEvalModel):
    kind: Literal['meanScoreDrop']
    baseline: float
    current: float


class RuleFlip(BaseEvalModel):
    kind: Literal['ruleFlip']
    case_id: str
    rule: str


class CaseScoreDrop(BaseEvalModel):
    kind: Literal['caseScoreDrop']
    case_id: str
    baseline: float
    current: float


class ErrorRate(BaseEvalModel):
    kind: Literal['errorRate']
    error_count: int
    case_count: int


class RecentBestDrop(BaseEvalModel):
    kind: Literal['recentBestDrop']
    recent_best: float
    current: float


Regression = Annotated[
    Union[
        MeanScoreDrop,
        RuleFlip,
        CaseScoreDrop,
        ErrorRate,
        RecentBestDrop,
    ],
    Field(discriminator='kind'),
]


class EvalRunPayload(BaseEvalModel):
    """Payload for POST /evals/runs."""
    run: 'Run'
    results: list[CaseResult]


class Run(BaseEvalModel):
    """Metadata for an eval run."""
    label: Literal['scheduled', 'manual']
    git_sha: str
    git_ref: str
    app_model: str
    judge_model: str
    cases_version: int
    started_at: int
    finished_at: int
    status: Literal['completed', 'errored']
    summary: RunSummary
    regressions: list[Regression]
    baseline_run_id: Optional[str] = None


class CasesFile(BaseEvalModel):
    """Structure of evals/cases.json."""
    version: int
    cases: list[EvalCase]
