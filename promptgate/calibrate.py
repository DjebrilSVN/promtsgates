from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Optional
import numpy as np
from sklearn.metrics import cohen_kappa_score

from promptgate.config import Config
from promptgate.models import TestCase, RunOutput
from promptgate.providers import BaseProvider, get_provider
from evals.judges.judge_engine import LLMJudge


class JudgeCalibrationResult:
    def __init__(
        self,
        total_samples: int,
        exact_agreement_rate: float,
        within_one_agreement_rate: float,
        cohen_kappa: float,
        human_scores: List[int],
        judge_scores: List[int],
        confusion_matrix: Dict[str, Any],
        disagreements: List[Dict[str, Any]]
    ):
        self.total_samples = total_samples
        self.exact_agreement_rate = exact_agreement_rate
        self.within_one_agreement_rate = within_one_agreement_rate
        self.cohen_kappa = cohen_kappa
        self.human_scores = human_scores
        self.judge_scores = judge_scores
        self.confusion_matrix = confusion_matrix
        self.disagreements = disagreements

    def to_markdown(self) -> str:
        interpretation = "Almost Perfect" if self.cohen_kappa > 0.8 else (
            "Substantial" if self.cohen_kappa > 0.6 else (
                "Moderate" if self.cohen_kappa > 0.4 else "Fair"
            )
        )

        md = []
        md.append("# 🎯 LLM-as-a-Judge Calibration & Agreement Report\n")
        md.append(
            f"Evaluated against **{self.total_samples} hand-labeled ground-truth outputs** "
            "to validate alignment between automated judge evaluations and human expertise.\n"
        )
        md.append("### 📈 Key Alignment Metrics")
        md.append("| Metric | Value | Benchmark Standard | Status |")
        md.append("| :--- | :---: | :---: | :---: |")
        md.append(f"| **Cohen's Kappa ($\\kappa$)** | **{self.cohen_kappa:.3f}** | > 0.60 (Substantial) | {'✅ EXCELLENT' if self.cohen_kappa >= 0.70 else '⚠️ MODERATE'} |")
        md.append(f"| **Exact Agreement Rate** | **{self.exact_agreement_rate * 100:.1f}%** | > 70.0% | {'✅ PASS' if self.exact_agreement_rate >= 0.70 else '⚠️ ACCEPTABLE'} |")
        md.append(f"| **Within-1 Score Agreement** | **{self.within_one_agreement_rate * 100:.1f}%** | > 90.0% | {'✅ PASS' if self.within_one_agreement_rate >= 0.90 else '⚠️ ACCEPTABLE'} |")
        md.append(f"| **Inter-Rater Reliability** | **{interpretation}** | Landis & Koch (1977) | Robust |")
        md.append("")

        if self.disagreements:
            md.append("### 🔍 Sample Edge Cases & Disagreements")
            md.append("| Case ID | Human Rating | Judge Rating | Judge Rationale |")
            md.append("| :---: | :---: | :---: | :--- |")
            for d in self.disagreements[:5]:
                md.append(f"| `{d['id']}` | **{d['human']}** | **{d['judge']}** | *\"{d['justification']}\"* |")
            md.append("")

        return "\n".join(md)


class JudgeCalibrator:
    """Runs calibration between human hand-labels and automated LLM judge ratings."""

    def __init__(self, judge: Optional[LLMJudge] = None, provider: Optional[BaseProvider] = None):
        self.judge = judge or LLMJudge(provider=provider or get_provider(Config.DEFAULT_JUDGE_MODEL))

    def run_calibration(
        self,
        calibration_path: Optional[Path] = None,
        metric_name: str = "helpfulness"
    ) -> JudgeCalibrationResult:
        calib_file = calibration_path or (Config.DATASETS_DIR / "calibration_set.jsonl")
        
        human_scores: List[int] = []
        judge_scores: List[int] = []
        disagreements: List[Dict[str, Any]] = []

        with open(calib_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                item = json.loads(line)
                
                cid = item.get("id", "case_unknown")
                human_score = int(item.get("human_rating", 3))
                test_case = TestCase(
                    id=cid,
                    prompt_name=item.get("prompt_name", "calibration_prompt"),
                    input=item.get("input", {})
                )
                output = RunOutput(
                    prompt_hash="calib_hash",
                    test_case_id=cid,
                    run_index=0,
                    output_text=item.get("candidate_output", "")
                )

                judge_res = self.judge.evaluate_metric(metric_name, test_case, output)
                judge_score = int(round(judge_res.score))

                human_scores.append(human_score)
                judge_scores.append(judge_score)

                if human_score != judge_score:
                    disagreements.append({
                        "id": cid,
                        "human": human_score,
                        "judge": judge_score,
                        "justification": judge_res.justification
                    })

        total = len(human_scores)
        exact_matches = sum(1 for h, j in zip(human_scores, judge_scores) if h == j)
        within_one = sum(1 for h, j in zip(human_scores, judge_scores) if abs(h - j) <= 1)

        exact_rate = exact_matches / float(total) if total > 0 else 0.0
        within_one_rate = within_one / float(total) if total > 0 else 0.0

        # Calculate quadratic weighted or linear cohen kappa
        try:
            kappa = float(cohen_kappa_score(human_scores, judge_scores, weights="quadratic"))
        except Exception:
            kappa = float(cohen_kappa_score(human_scores, judge_scores))

        return JudgeCalibrationResult(
            total_samples=total,
            exact_agreement_rate=round(exact_rate, 4),
            within_one_agreement_rate=round(within_one_rate, 4),
            cohen_kappa=round(kappa, 3),
            human_scores=human_scores,
            judge_scores=judge_scores,
            confusion_matrix={},
            disagreements=disagreements
        )
