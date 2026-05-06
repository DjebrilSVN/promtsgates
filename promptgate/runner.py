from __future__ import annotations
import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from promptgate.config import Config
from promptgate.models import (
    PromptDefinition,
    TestCase,
    RunOutput,
    CaseEvaluation,
    SuiteRunResult,
    CheckResult,
    JudgeResult
)
from promptgate.cache import EvalCache
from promptgate.providers import BaseProvider, get_provider
from evals.checks import run_deterministic_checks
from evals.judges.judge_engine import LLMJudge
from promptgate.stats import compute_metric_summary


class EvalRunner:
    """Executes prompt evaluation suites against golden datasets."""

    def __init__(
        self,
        provider: Optional[BaseProvider] = None,
        judge_provider: Optional[BaseProvider] = None,
        cache: Optional[EvalCache] = None,
        repetitions: Optional[int] = None,
        use_cache: bool = True
    ):
        self.provider = provider
        self.judge_provider = judge_provider
        self.cache = cache or EvalCache()
        self.repetitions = repetitions or Config.DEFAULT_REPETITIONS
        self.use_cache = use_cache

    @staticmethod
    def load_prompt(prompt_path: Path) -> PromptDefinition:
        """Loads a PromptDefinition from a YAML file."""
        with open(prompt_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return PromptDefinition(**data)

    @staticmethod
    def load_dataset(dataset_path: Path) -> List[TestCase]:
        """Loads test cases from a JSONL dataset file."""
        cases = []
        with open(dataset_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                d = json.loads(line)
                cases.append(TestCase(**d))
        return cases

    def run_suite(
        self,
        prompt: PromptDefinition,
        test_cases: List[TestCase],
        metrics: Optional[List[str]] = None,
        smoke_count: Optional[int] = None
    ) -> SuiteRunResult:
        """Runs the entire evaluation suite for a prompt against test cases."""
        if smoke_count and smoke_count > 0:
            test_cases = test_cases[:smoke_count]

        provider = self.provider or get_provider(prompt.model)
        judge = LLMJudge(provider=self.judge_provider or get_provider(Config.DEFAULT_JUDGE_MODEL))
        
        target_metrics = metrics or ["faithfulness", "helpfulness", "tone_and_empathy", "policy_adherence"]
        
        case_evaluations: List[CaseEvaluation] = []
        total_cost = 0.0
        total_latency = 0.0
        total_tokens = 0
        cache_hits = 0
        total_runs = 0

        # Metric score collectors
        metric_scores: Dict[str, List[float]] = {m: [] for m in target_metrics}
        hard_check_passes = 0
        total_hard_checks = 0

        for case in test_cases:
            outputs: List[RunOutput] = []
            case_hard_checks: List[CheckResult] = []
            case_judge_results: List[JudgeResult] = []

            # Populate prompt template with test case input
            formatted_user_prompt = prompt.user_prompt
            for k, v in case.input.items():
                placeholder = f"{{{{{k}}}}}"
                val_str = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
                formatted_user_prompt = formatted_user_prompt.replace(placeholder, val_str)

            # Production repetitions (to capture stochastic variance)
            reps = 1 if prompt.temperature == 0.0 else self.repetitions

            for rep_idx in range(reps):
                total_runs += 1
                cache_key, prompt_hash = EvalCache.compute_key(
                    prompt_content=f"{prompt.system_prompt}\n{formatted_user_prompt}",
                    input_data=case.input,
                    model=prompt.model,
                    temperature=prompt.temperature,
                    run_index=rep_idx
                )

                cached_data = self.cache.get(cache_key) if self.use_cache else None
                if cached_data:
                    cache_hits += 1
                    run_out = RunOutput(
                        prompt_hash=prompt_hash,
                        test_case_id=case.id,
                        run_index=rep_idx,
                        output_text=cached_data["output_text"],
                        latency_ms=cached_data["latency_ms"],
                        prompt_tokens=cached_data["prompt_tokens"],
                        completion_tokens=cached_data["completion_tokens"],
                        cost_usd=cached_data["cost_usd"],
                        cached=True
                    )
                else:
                    llm_resp = provider.generate(
                        system_prompt=prompt.system_prompt,
                        user_prompt=formatted_user_prompt,
                        model=prompt.model,
                        temperature=prompt.temperature,
                        max_tokens=prompt.max_tokens,
                        response_schema=prompt.response_schema
                    )

                    run_out = RunOutput(
                        prompt_hash=prompt_hash,
                        test_case_id=case.id,
                        run_index=rep_idx,
                        output_text=llm_resp.text,
                        latency_ms=llm_resp.latency_ms,
                        prompt_tokens=llm_resp.prompt_tokens,
                        completion_tokens=llm_resp.completion_tokens,
                        cost_usd=llm_resp.cost_usd,
                        cached=False
                    )

                    if self.use_cache:
                        self.cache.set(
                            cache_key=cache_key,
                            prompt_hash=prompt_hash,
                            model=prompt.model,
                            output_text=llm_resp.text,
                            prompt_tokens=llm_resp.prompt_tokens,
                            completion_tokens=llm_resp.completion_tokens,
                            latency_ms=llm_resp.latency_ms,
                            cost_usd=llm_resp.cost_usd
                        )

                outputs.append(run_out)
                total_cost += run_out.cost_usd
                total_latency += run_out.latency_ms
                total_tokens += (run_out.prompt_tokens + run_out.completion_tokens)

                # Run deterministic checks on output
                checks, parsed_json = run_deterministic_checks(prompt, case, run_out)
                run_out.parsed_json = parsed_json
                case_hard_checks.extend(checks)

                for chk in checks:
                    if chk.is_hard_gate:
                        total_hard_checks += 1
                        if chk.passed:
                            hard_check_passes += 1

                # If hard checks passed, run LLM Judge
                all_hard_passed = all(c.passed for c in checks if c.is_hard_gate)
                if all_hard_passed:
                    j_results = judge.evaluate_all(target_metrics, case, run_out)
                    case_judge_results.extend(j_results)
                    for jr in j_results:
                        metric_scores[jr.metric_name].append(jr.score)
                else:
                    # Penalize failed hard checks with min score 1.0 on judge metrics
                    for m in target_metrics:
                        failed_chk = next((c for c in checks if not c.passed and c.is_hard_gate), None)
                        reason = failed_chk.details if failed_chk else "Failed hard checks"
                        case_judge_results.append(
                            JudgeResult(
                                metric_name=m,
                                score=1.0,
                                justification=f"Hard check failure: {reason}",
                                passed=False
                            )
                        )
                        metric_scores[m].append(1.0)

            case_evaluations.append(
                CaseEvaluation(
                    test_case_id=case.id,
                    input=case.input,
                    expected_output=case.expected_output,
                    tags=case.tags,
                    outputs=outputs,
                    deterministic_checks=case_hard_checks,
                    judge_results=case_judge_results
                )
            )

        # Summarize metrics
        hard_pass_rate = hard_check_passes / float(total_hard_checks) if total_hard_checks > 0 else 1.0
        cache_hit_rate = cache_hits / float(total_runs) if total_runs > 0 else 0.0
        avg_latency = total_latency / float(total_runs) if total_runs > 0 else 0.0

        summaries = {
            m: compute_metric_summary(scores)
            for m, scores in metric_scores.items()
        }

        return SuiteRunResult(
            prompt_name=prompt.name,
            prompt_version=prompt.version,
            prompt_hash=prompt.get_content_hash(),
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            case_evaluations=case_evaluations,
            hard_pass_rate=round(hard_pass_rate, 4),
            metrics=summaries,
            total_cost_usd=round(total_cost, 6),
            avg_latency_ms=round(avg_latency, 1),
            total_tokens=total_tokens,
            cache_hit_rate=round(cache_hit_rate, 4)
        )
