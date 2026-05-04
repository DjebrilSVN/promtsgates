from __future__ import annotations
import math
from typing import Any, Dict, Optional
from promptgate.models import CheckResult


def check_exact_or_numeric_match(
    parsed_json: Optional[Dict[str, Any]],
    expected_dict: Optional[Dict[str, Any]],
    tolerance: float = 0.01
) -> CheckResult:
    """Checks exact matches and numeric tolerances on expected key-value pairs."""
    if not expected_dict:
        return CheckResult(
            check_name="field_match",
            passed=True,
            score=1.0,
            details="No ground-truth expected fields specified.",
            is_hard_gate=False
        )

    if not parsed_json or not isinstance(parsed_json, dict):
        return CheckResult(
            check_name="field_match",
            passed=False,
            score=0.0,
            details="Cannot perform field match: parsed output is not a JSON object.",
            is_hard_gate=True
        )

    matched = 0
    total = len(expected_dict)
    mismatches = []

    for key, expected_val in expected_dict.items():
        if key not in parsed_json:
            mismatches.append(f"Missing key '{key}'")
            continue
        
        actual_val = parsed_json[key]

        # Numeric comparison
        if isinstance(expected_val, (int, float)) and isinstance(actual_val, (int, float)):
            if math.isclose(float(expected_val), float(actual_val), abs_tol=tolerance):
                matched += 1
            else:
                mismatches.append(f"Key '{key}': expected {expected_val}, got {actual_val}")
        # String case-insensitive comparison
        elif isinstance(expected_val, str) and isinstance(actual_val, str):
            if expected_val.strip().lower() == actual_val.strip().lower():
                matched += 1
            else:
                mismatches.append(f"Key '{key}': expected '{expected_val}', got '{actual_val}'")
        else:
            if expected_val == actual_val:
                matched += 1
            else:
                mismatches.append(f"Key '{key}': expected {expected_val}, got {actual_val}")

    score = matched / float(total) if total > 0 else 1.0
    passed = score >= 0.99

    details = "All expected fields matched exactly." if passed else f"Field mismatches: {', '.join(mismatches[:3])}"
    return CheckResult(
        check_name="field_match",
        passed=passed,
        score=score,
        details=details,
        is_hard_gate=False
    )
