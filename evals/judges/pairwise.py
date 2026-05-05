from __future__ import annotations
import json
import random
import re
from typing import Any, Dict, Optional
from promptgate.config import Config
from promptgate.models import TestCase
from promptgate.providers import BaseProvider, get_provider


class PairwiseComparisonResult:
    def __init__(
        self,
        winner: str,  # 'candidate', 'baseline', or 'tie'
        raw_choice: str,
        justification: str,
        presentation_order: str  # 'candidate_first' or 'baseline_first'
    ):
        self.winner = winner
        self.raw_choice = raw_choice
        self.justification = justification
        self.presentation_order = presentation_order

    def to_dict(self) -> Dict[str, Any]:
        return {
            "winner": self.winner,
            "raw_choice": self.raw_choice,
            "justification": self.justification,
            "presentation_order": self.presentation_order
        }


class PairwiseJudge:
    """Pairwise comparison judge with randomized presentation to cancel position bias."""

    def __init__(self, provider: Optional[BaseProvider] = None, judge_model: Optional[str] = None):
        self.judge_model = judge_model or Config.DEFAULT_JUDGE_MODEL
        self.provider = provider or get_provider(self.judge_model)

    def compare(
        self,
        test_case: TestCase,
        candidate_output: str,
        baseline_output: str,
        criteria: str = "Overall quality, correctness, helpfulness, and tone"
    ) -> PairwiseComparisonResult:
        """Compares Candidate vs Baseline with randomized order A/B."""
        # Randomize presentation
        candidate_first = random.choice([True, False])
        
        if candidate_first:
            resp_a = candidate_output
            resp_b = baseline_output
            order_desc = "candidate_first"
        else:
            resp_a = baseline_output
            resp_b = candidate_output
            order_desc = "baseline_first"

        system_prompt = (
            "You are an expert impartial judge performing a blind pairwise evaluation between two AI responses.\n"
            "Compare Response A and Response B based on the specified criteria.\n"
            "Return ONLY a JSON object:\n"
            "  \"winner\": \"A\", \"B\", or \"TIE\"\n"
            "  \"justification\": \"one sentence explaining why one is superior\""
        )

        user_prompt = f"""
Criteria: {criteria}

[USER INPUT / CONTEXT]:
{json.dumps(test_case.input, indent=2)}

[RESPONSE A]:
{resp_a}

[RESPONSE B]:
{resp_b}

JSON output:
{{"winner": "A" | "B" | "TIE", "justification": "<one line justification>"}}
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
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
                cleaned = re.sub(r"\n?```$", "", cleaned)
                cleaned = cleaned.strip()

            parsed = json.loads(cleaned)
            raw_choice = parsed.get("winner", "TIE").upper()
            justification = parsed.get("justification", "No justification provided.")

            if raw_choice == "A":
                winner = "candidate" if candidate_first else "baseline"
            elif raw_choice == "B":
                winner = "baseline" if candidate_first else "candidate"
            else:
                winner = "tie"

            return PairwiseComparisonResult(
                winner=winner,
                raw_choice=raw_choice,
                justification=justification,
                presentation_order=order_desc
            )

        except Exception as e:
            return PairwiseComparisonResult(
                winner="tie",
                raw_choice="TIE",
                justification=f"Pairwise evaluation error: {str(e)}",
                presentation_order=order_desc
            )
