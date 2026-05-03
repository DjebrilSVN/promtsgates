from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PromptDefinition(BaseModel):
    name: str
    version: str
    description: str = ""
    model: str = "gemini-2.5-flash"
    temperature: float = 0.0
    max_tokens: int = 1000
    system_prompt: str = ""
    user_prompt: str
    response_schema: Optional[Dict[str, Any]] = None
    tags: List[str] = Field(default_factory=list)
    changelog: str = ""

    def get_content_hash(self) -> str:
        import hashlib
        payload = f"{self.name}:{self.version}:{self.model}:{self.temperature}:{self.system_prompt}:{self.user_prompt}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class TestCase(BaseModel):
    id: str
    prompt_name: str
    input: Dict[str, Any]
    expected_output: Optional[Any] = None
    rubric: Optional[Dict[str, Any]] = None
    tags: List[str] = Field(default_factory=list)


class CheckResult(BaseModel):
    check_name: str
    passed: bool
    score: float = 1.0  # 0.0 to 1.0
    details: str = ""
    is_hard_gate: bool = True


class JudgeResult(BaseModel):
    metric_name: str
    score: float  # 1.0 to 5.0
    justification: str
    passed: bool = True


class RunOutput(BaseModel):
    prompt_hash: str
    test_case_id: str
    run_index: int
    output_text: str
    parsed_json: Optional[Dict[str, Any]] = None
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    cached: bool = False
    error: Optional[str] = None


class CaseEvaluation(BaseModel):
    test_case_id: str
    input: Dict[str, Any]
    expected_output: Optional[Any] = None
    tags: List[str] = Field(default_factory=list)
    outputs: List[RunOutput]
    deterministic_checks: List[CheckResult]
    judge_results: List[JudgeResult]


class MetricSummary(BaseModel):
    mean: float
    ci_lower: float
    ci_upper: float
    std: float
    n: int


class DeltaComparison(BaseModel):
    metric_name: str
    baseline_mean: float
    candidate_mean: float
    delta: float
    ci_lower: float
    ci_upper: float
    p_value: Optional[float] = None
    regressed: bool = False
    reason: str = ""


class RegressedCase(BaseModel):
    test_case_id: str
    input_preview: str
    baseline_output: str
    candidate_output: str
    metric_name: str
    baseline_score: float
    candidate_score: float
    delta: float
    explanation: str


class SuiteRunResult(BaseModel):
    prompt_name: str
    prompt_version: str
    prompt_hash: str
    timestamp: str
    case_evaluations: List[CaseEvaluation]
    hard_pass_rate: float
    metrics: Dict[str, MetricSummary]
    total_cost_usd: float
    avg_latency_ms: float
    total_tokens: int
    cache_hit_rate: float


class GateEvaluation(BaseModel):
    passed: bool
    prompt_name: str
    candidate_version: str
    baseline_version: str
    hard_failures: List[str] = Field(default_factory=list)
    metric_deltas: List[DeltaComparison] = Field(default_factory=list)
    worst_cases: List[RegressedCase] = Field(default_factory=list)
    summary_markdown: str = ""
