from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Dict, List, Optional
import yaml

from promptgate.config import Config
from promptgate.models import JudgeResult, TestCase, RunOutput
from promptgate.providers import BaseProvider, get_provider


class LLMJudge:
    """Rubric-based LLM Judge evaluator."""

    def __init__(self, provider: Optional[BaseProvider] = None, judge_model: Optional[str] = None):
        self.judge_model = judge_model or Config.DEFAULT_JUDGE_MODEL
        self.provider = provider or get_provider(self.judge_model)
        self.rubrics = self._load_rubrics()

    def _load_rubrics(self) -> Dict[str, Any]:
        rubric_path = Config.JUDGES_DIR / "rubrics.yaml"
        if rubric_path.exists():
            with open(rubric_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data.get("metrics", {})
        return {}

    def evaluate_metric(
        self,
        metric_name: str,
        test_case: TestCase,
        output: RunOutput
    ) -> JudgeResult:
        """Evaluates a single metric on a 1-5 scale with a one-line justification."""
        metric_info = self.rubrics.get(metric_name)
        if not metric_info:
            return JudgeResult(
                metric_name=metric_name,
                score=5.0,
                justification="No rubric defined; defaulted to full score.",
                passed=True
            )

        scale_desc = "\n".join([f"- Level {k}: {v}" for k, v in metric_info.get("scale", {}).items()])
        
        system_prompt = (
            "You are an expert impartial LLM judge evaluating AI model outputs for a production system.\n"
            "Score the output objectively based strictly on the provided rubric.\n"
            "You must return ONLY a JSON object with two fields:\n"
            "  \"score\": integer from 1 to 5\n"
            "  \"justification\": a single concise sentence explaining the score"
        )

        user_prompt = f"""
Evaluation Rubric: {metric_name.upper()}
Description: {metric_info.get('description', '')}

Grading Scale:
{scale_desc}

[TEST CASE INPUT]:
{json.dumps(test_case.input, indent=2)}

[MODEL OUTPUT UNDER EVALUATION]:
{output.output_text}

Provide your evaluation in valid JSON:
{{"score": <1-5>, "justification": "<concise one-line rationale>"}}
"""

        try:
            resp = self.provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=self.judge_model,
                temperature=0.0,
                max_tokens=300
            )

            cleaned = resp.text.strip()
            # Clean markdown if present
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
                cleaned = re.sub(r"\n?```$", "", cleaned)
                cleaned = cleaned.strip()

            parsed = json.loads(cleaned)
            score = float(parsed.get("score", 3.0))
            justification = str(parsed.get("justification", "No justification provided."))
            
            # Enforce 1.0 to 5.0 bounds
            score = max(1.0, min(5.0, score))
            passed = score >= 3.5

            return JudgeResult(
                metric_name=metric_name,
                score=score,
                justification=justification,
                passed=passed
            )

        except Exception as e:
            return JudgeResult(
                metric_name=metric_name,
                score=3.0,
                justification=f"Judge evaluation failed: {str(e)}",
                passed=False
            )

    def evaluate_all(
        self,
        metrics: List[str],
        test_case: TestCase,
        output: RunOutput
    ) -> List[JudgeResult]:
        """Runs evaluation across all requested metrics for an output."""
        return [self.evaluate_metric(m, test_case, output) for m in metrics]
