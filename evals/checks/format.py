from __future__ import annotations
import re
from promptgate.models import CheckResult


def check_word_count(
    output_text: str,
    max_words: int = 150,
    min_words: int = 5,
    is_hard_gate: bool = False
) -> CheckResult:
    """Checks word count constraints."""
    words = re.findall(r"\b\w+\b", output_text)
    count = len(words)
    
    if count > max_words:
        return CheckResult(
            check_name="format_word_count",
            passed=False,
            score=max(0.0, 1.0 - (count - max_words) / float(max_words)),
            details=f"Exceeded maximum word count: {count} words (limit: {max_words})",
            is_hard_gate=is_hard_gate
        )
    if count < min_words:
        return CheckResult(
            check_name="format_word_count",
            passed=False,
            score=0.0,
            details=f"Below minimum word count: {count} words (minimum: {min_words})",
            is_hard_gate=is_hard_gate
        )
        
    return CheckResult(
        check_name="format_word_count",
        passed=True,
        score=1.0,
        details=f"Word count within limits: {count} words ({min_words}-{max_words})",
        is_hard_gate=is_hard_gate
    )


def check_non_empty(output_text: str) -> CheckResult:
    """Verifies output is not blank."""
    if not output_text or not output_text.strip():
        return CheckResult(
            check_name="format_non_empty",
            passed=False,
            score=0.0,
            details="Output text is empty or only whitespace.",
            is_hard_gate=True
        )
    return CheckResult(
        check_name="format_non_empty",
        passed=True,
        score=1.0,
        details="Output is non-empty.",
        is_hard_gate=True
    )
