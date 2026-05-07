from __future__ import annotations
import json
from typing import Dict, List, Optional
from promptgate.config import Config
from promptgate.models import (
    SuiteRunResult,
    GateEvaluation,
    DeltaComparison,
    RegressedCase
)
from promptgate.stats import compute_delta_comparison


class RegressionGate:
    """Evaluates whether a candidate prompt run regresses against a baseline run."""

    def __init__(self, thresholds=None):
        self.thresholds = thresholds or Config.THRESHOLDS

    def evaluate(
        self,
        candidate_result: SuiteRunResult,
        baseline_result: SuiteRunResult
    ) -> GateEvaluation:
        hard_failures: List[str] = []
        metric_deltas: List[DeltaComparison] = []

        # 1. Hard check gate: candidate hard_pass_rate must be 100% (or not decrease from baseline)
        if candidate_result.hard_pass_rate < self.thresholds.min_hard_pass_rate:
            hard_failures.append(
                f"Hard check pass rate dropped to {candidate_result.hard_pass_rate * 100:.1f}% "
                f"(Required: {self.thresholds.min_hard_pass_rate * 100:.1f}%). "
                "One or more deterministic schema, policy, or safety checks failed."
            )

        if candidate_result.hard_pass_rate < baseline_result.hard_pass_rate:
            hard_failures.append(
                f"Hard pass rate degraded from {baseline_result.hard_pass_rate * 100:.1f}% (baseline) "
                f"to {candidate_result.hard_pass_rate * 100:.1f}% (candidate)."
            )

        # 2. Extract raw scores per metric for candidate and baseline
        candidate_scores_by_metric: Dict[str, List[float]] = {}
        candidate_case_scores: Dict[str, Dict[str, float]] = {}  # case_id -> {metric -> avg_score}

        for c_eval in candidate_result.case_evaluations:
            case_id = c_eval.test_case_id
            candidate_case_scores[case_id] = {}
            for j_res in c_eval.judge_results:
                candidate_scores_by_metric.setdefault(j_res.metric_name, []).append(j_res.score)
                # Track per-case score
                candidate_case_scores[case_id].setdefault(j_res.metric_name, []).append(j_res.score)

        baseline_scores_by_metric: Dict[str, List[float]] = {}
        baseline_case_scores: Dict[str, Dict[str, float]] = {}

        for b_eval in baseline_result.case_evaluations:
            case_id = b_eval.test_case_id
            baseline_case_scores[case_id] = {}
            for j_res in b_eval.judge_results:
                baseline_scores_by_metric.setdefault(j_res.metric_name, []).append(j_res.score)
                baseline_case_scores[case_id].setdefault(j_res.metric_name, []).append(j_res.score)

        # Average per-case scores
        cand_case_means = {
            cid: {m: sum(scores) / len(scores) for m, scores in m_dict.items()}
            for cid, m_dict in candidate_case_scores.items()
        }
        base_case_means = {
            cid: {m: sum(scores) / len(scores) for m, scores in m_dict.items()}
            for cid, m_dict in baseline_case_scores.items()
        }

        # 3. Statistical delta comparison for each metric
        all_metrics = set(candidate_scores_by_metric.keys()) | set(baseline_scores_by_metric.keys())
        any_metric_regressed = False

        for metric in sorted(all_metrics):
            b_scores = baseline_scores_by_metric.get(metric, [])
            c_scores = candidate_scores_by_metric.get(metric, [])
            
            comparison = compute_delta_comparison(
                metric_name=metric,
                baseline_scores=b_scores,
                candidate_scores=c_scores,
                threshold_ci_lower=self.thresholds.max_allowable_drop_ci_lower,
                confidence_level=1.0 - self.thresholds.significance_level_p
            )
            metric_deltas.append(comparison)

            if comparison.regressed:
                any_metric_regressed = True

        # 4. Identify worst 5 regressed test cases
        case_regressions: List[RegressedCase] = []

        # Find map of candidate and baseline outputs for each case
        candidate_case_map = {c.test_case_id: c for c in candidate_result.case_evaluations}
        baseline_case_map = {b.test_case_id: b for b in baseline_result.case_evaluations}

        common_case_ids = set(candidate_case_map.keys()) & set(baseline_case_map.keys())

        for cid in common_case_ids:
            c_case = candidate_case_map[cid]
            b_case = baseline_case_map[cid]

            c_means = cand_case_means.get(cid, {})
            b_means = base_case_means.get(cid, {})

            # Calculate overall case average
            if c_means and b_means:
                c_avg = sum(c_means.values()) / len(c_means)
                b_avg = sum(b_means.values()) / len(b_means)
                delta = c_avg - b_avg

                if delta < -0.05:  # Noticeable regression
                    # Find worst individual metric for this case
                    worst_m = min(c_means.keys(), key=lambda k: c_means.get(k, 0) - b_means.get(k, 0))
                    
                    # Reason from candidate judge
                    worst_reason = "Performance degraded compared to baseline."
                    for j_res in c_case.judge_results:
                        if j_res.metric_name == worst_m and j_res.justification:
                            worst_reason = j_res.justification
                            break

                    input_preview = json.dumps(c_case.input, ensure_ascii=False)
                    if len(input_preview) > 120:
                        input_preview = input_preview[:117] + "..."

                    b_out = b_case.outputs[0].output_text if b_case.outputs else ""
                    c_out = c_case.outputs[0].output_text if c_case.outputs else ""

                    case_regressions.append(
                        RegressedCase(
                            test_case_id=cid,
                            input_preview=input_preview,
                            baseline_output=b_out,
                            candidate_output=c_out,
                            metric_name=worst_m,
                            baseline_score=round(b_means.get(worst_m, 5.0), 2),
                            candidate_score=round(c_means.get(worst_m, 1.0), 2),
                            delta=round(delta, 2),
                            explanation=worst_reason
                        )
                    )

        # Sort by most negative delta first
        case_regressions.sort(key=lambda x: x.delta)
        worst_5 = case_regressions[:5]

        passed = (len(hard_failures) == 0) and (not any_metric_regressed)

        return GateEvaluation(
            passed=passed,
            prompt_name=candidate_result.prompt_name,
            candidate_version=candidate_result.prompt_version,
            baseline_version=baseline_result.prompt_version,
            hard_failures=hard_failures,
            metric_deltas=metric_deltas,
            worst_cases=worst_5
        )
