from __future__ import annotations
import numpy as np
from typing import List, Tuple, Optional
from scipy import stats
from promptgate.models import MetricSummary, DeltaComparison


def compute_metric_summary(scores: List[float], confidence_level: float = 0.95, n_resamples: int = 1000) -> MetricSummary:
    """Computes sample mean, std, and bootstrap confidence interval for a list of scores."""
    if not scores:
        return MetricSummary(mean=0.0, ci_lower=0.0, ci_upper=0.0, std=0.0, n=0)

    arr = np.array(scores, dtype=float)
    n = len(arr)
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1)) if n > 1 else 0.0

    if n < 3 or np.all(arr == arr[0]):
        return MetricSummary(mean=mean, ci_lower=mean, ci_upper=mean, std=std, n=n)

    # Use scipy bootstrap
    try:
        res = stats.bootstrap(
            (arr,),
            np.mean,
            confidence_level=confidence_level,
            n_resamples=n_resamples,
            method="percentile"
        )
        ci_lower = float(res.confidence_interval.low)
        ci_upper = float(res.confidence_interval.high)
    except Exception:
        # Fallback to normal approximation
        se = std / np.sqrt(n) if n > 0 else 0.0
        z = 1.96
        ci_lower = mean - z * se
        ci_upper = mean + z * se

    return MetricSummary(
        mean=round(mean, 3),
        ci_lower=round(ci_lower, 3),
        ci_upper=round(ci_upper, 3),
        std=round(std, 3),
        n=n
    )


def compute_delta_comparison(
    metric_name: str,
    baseline_scores: List[float],
    candidate_scores: List[float],
    threshold_ci_lower: float = -0.20,
    confidence_level: float = 0.95,
    n_resamples: int = 2000
) -> DeltaComparison:
    """
    Computes the bootstrap difference of means (Candidate - Baseline).
    Determines if candidate statistically regresses beyond threshold_ci_lower.
    """
    base_arr = np.array(baseline_scores, dtype=float)
    cand_arr = np.array(candidate_scores, dtype=float)

    base_mean = float(np.mean(base_arr)) if len(base_arr) > 0 else 0.0
    cand_mean = float(np.mean(cand_arr)) if len(cand_arr) > 0 else 0.0
    delta = cand_mean - base_mean

    n_base = len(base_arr)
    n_cand = len(cand_arr)

    if n_base == 0 or n_cand == 0:
        return DeltaComparison(
            metric_name=metric_name,
            baseline_mean=round(base_mean, 3),
            candidate_mean=round(cand_mean, 3),
            delta=round(delta, 3),
            ci_lower=round(delta, 3),
            ci_upper=round(delta, 3),
            p_value=1.0,
            regressed=False,
            reason="Insufficient data for delta calculation."
        )

    # Bootstrap difference of means
    rng = np.random.default_rng(seed=42)
    boot_deltas = np.empty(n_resamples)

    for i in range(n_resamples):
        sample_base = rng.choice(base_arr, size=n_base, replace=True)
        sample_cand = rng.choice(cand_arr, size=n_cand, replace=True)
        boot_deltas[i] = np.mean(sample_cand) - np.mean(sample_base)

    alpha = 1.0 - confidence_level
    ci_lower = float(np.percentile(boot_deltas, 100 * (alpha / 2.0)))
    ci_upper = float(np.percentile(boot_deltas, 100 * (1.0 - alpha / 2.0)))

    # Two-sided empirical p-value for H0: delta = 0
    p_pos = np.mean(boot_deltas >= 0)
    p_neg = np.mean(boot_deltas <= 0)
    p_value = float(min(1.0, 2.0 * min(p_pos, p_neg)))

    # Regression detection:
    # 1. Delta lower bound drops below allowable margin (e.g. -0.20)
    # OR 2. Upper bound is strictly negative AND delta < -0.10 (statistically significant drop)
    regressed = False
    reason = "Quality maintained within acceptable statistical variance."

    if ci_lower < threshold_ci_lower:
        regressed = True
        reason = (
            f"Statistically significant regression: 95% CI lower bound ({ci_lower:.3f}) "
            f"is worse than threshold ({threshold_ci_lower:.3f})."
        )
    elif ci_upper < 0.0 and delta < -0.10:
        regressed = True
        reason = f"Statistically significant drop (p={p_value:.4f}, delta={delta:.3f}, 95% CI [{ci_lower:.3f}, {ci_upper:.3f}])."

    return DeltaComparison(
        metric_name=metric_name,
        baseline_mean=round(base_mean, 3),
        candidate_mean=round(cand_mean, 3),
        delta=round(delta, 3),
        ci_lower=round(ci_lower, 3),
        ci_upper=round(ci_upper, 3),
        p_value=round(p_value, 4),
        regressed=regressed,
        reason=reason
    )
