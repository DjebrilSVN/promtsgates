from __future__ import annotations
import json
import re
from typing import Any, Dict, Optional, Tuple
from promptgate.models import CheckResult


def check_json_schema(
    output_text: str,
    required_fields: Optional[list] = None,
    allow_markdown_fence: bool = False
) -> Tuple[CheckResult, Optional[Dict[str, Any]]]:
    """Validates that output is parseable JSON and conforms to required schema keys."""
    cleaned = output_text.strip()
    
    # Check for markdown code fences if disallowed
    if not allow_markdown_fence and (cleaned.startswith("```") or "```json" in cleaned):
        return CheckResult(
            check_name="json_raw_format",
            passed=False,
            score=0.0,
            details="Output contains markdown code block fences (```json) when raw JSON was strictly requested.",
            is_hard_gate=True
        ), None

    # Strip fence if allowed
    if allow_markdown_fence and cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except Exception as e:
        return CheckResult(
            check_name="json_parse_validity",
            passed=False,
            score=0.0,
            details=f"Failed to parse JSON: {str(e)}",
            is_hard_gate=True
        ), None

    if not isinstance(data, dict):
        return CheckResult(
            check_name="json_object_type",
            passed=False,
            score=0.0,
            details=f"Expected JSON object (dict), got {type(data).__name__}",
            is_hard_gate=True
        ), None

    # Check required fields
    if required_fields:
        missing = [field for field in required_fields if field not in data]
        if missing:
            return CheckResult(
                check_name="json_required_fields",
                passed=False,
                score=max(0.0, (len(required_fields) - len(missing)) / len(required_fields)),
                details=f"Missing required fields: {missing}",
                is_hard_gate=True
            ), data

    return CheckResult(
        check_name="json_schema_validity",
        passed=True,
        score=1.0,
        details="Output is valid JSON containing all required fields.",
        is_hard_gate=True
    ), data
