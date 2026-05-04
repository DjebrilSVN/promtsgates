from __future__ import annotations
from typing import List, Tuple, Optional, Dict, Any
from promptgate.models import PromptDefinition, TestCase, RunOutput, CheckResult
from evals.checks.schema import check_json_schema
from evals.checks.policy import check_banned_phrases, check_pii_leakage
from evals.checks.format import check_word_count, check_non_empty
from evals.checks.budget import check_latency_budget, check_token_budget
from evals.checks.exact import check_exact_or_numeric_match


def run_deterministic_checks(
    prompt: PromptDefinition,
    test_case: TestCase,
    output: RunOutput
) -> Tuple[List[CheckResult], Optional[Dict[str, Any]]]:
    """Runs all applicable deterministic checks for a given test case and output."""
    results: List[CheckResult] = []
    parsed_json: Optional[Dict[str, Any]] = None

    # 1. Non-empty check (always applied)
    results.append(check_non_empty(output.output_text))

    # 2. Schema check (if prompt specifies response_schema or if test case expects structured JSON)
    is_json_prompt = (
        bool(prompt.response_schema)
        or "json" in prompt.user_prompt.lower()
        or "json" in prompt.system_prompt.lower()
        or isinstance(test_case.expected_output, dict)
    )

    if is_json_prompt:
        required_keys = []
        if prompt.response_schema and "required" in prompt.response_schema:
            required_keys = prompt.response_schema["required"]
        elif isinstance(test_case.expected_output, dict):
            required_keys = list(test_case.expected_output.keys())
        
        # Check strict json schema
        schema_result, parsed = check_json_schema(
            output.output_text,
            required_fields=required_keys,
            allow_markdown_fence=False
        )
        results.append(schema_result)
        parsed_json = parsed

    # 3. Policy & PII checks
    results.append(check_banned_phrases(output.output_text))
    results.append(check_pii_leakage(output.output_text))

    # 4. Word count check (for text-based generation like support replies)
    if not is_json_prompt:
        max_words = 150
        results.append(check_word_count(output.output_text, max_words=max_words, min_words=10))

    # 5. Exact field matching if expected structured output exists
    if is_json_prompt and isinstance(test_case.expected_output, dict):
        results.append(check_exact_or_numeric_match(parsed_json, test_case.expected_output))

    # 6. Budget checks
    results.append(check_latency_budget(output.latency_ms, max_latency_ms=4000.0))
    results.append(check_token_budget(output.prompt_tokens + output.completion_tokens, max_tokens=1500))

    return results, parsed_json
