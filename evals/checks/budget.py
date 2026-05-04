from __future__ import annotations
from promptgate.models import CheckResult


def check_latency_budget(latency_ms: float, max_latency_ms: float = 3000.0) -> CheckResult:
    """Verifies that response latency does not breach production SLA."""
    passed = latency_ms <= max_latency_ms
    score = 1.0 if passed else max(0.0, 1.0 - (latency_ms - max_latency_ms) / max_latency_ms)
    return CheckResult(
        check_name="budget_latency",
        passed=passed,
        score=score,
        details=f"Latency: {latency_ms:.1f}ms (threshold: {max_latency_ms:.1f}ms)",
        is_hard_gate=False
    )


def check_token_budget(total_tokens: int, max_tokens: int = 1500) -> CheckResult:
    """Verifies total tokens do not breach budget."""
    passed = total_tokens <= max_tokens
    score = 1.0 if passed else max(0.0, 1.0 - (total_tokens - max_tokens) / float(max_tokens))
    return CheckResult(
        check_name="budget_tokens",
        passed=passed,
        score=score,
        details=f"Tokens consumed: {total_tokens} (budget: {max_tokens})",
        is_hard_gate=False
    )
