import numpy as np
from promptgate.stats import compute_metric_summary, compute_delta_comparison


def test_compute_metric_summary():
    scores = [4.5, 4.8, 5.0, 4.6, 4.9, 5.0, 4.7]
    summary = compute_metric_summary(scores)
    assert summary.n == 7
    assert 4.5 <= summary.mean <= 5.0
    assert summary.ci_lower <= summary.mean <= summary.ci_upper


def test_delta_comparison_no_regression():
    base = [4.5, 4.6, 4.7, 4.8, 4.5, 4.6, 4.7]
    cand = [4.6, 4.7, 4.8, 4.8, 4.7, 4.6, 4.8]
    comp = compute_delta_comparison("helpfulness", base, cand, threshold_ci_lower=-0.20)
    assert comp.regressed is False
    assert comp.delta >= 0.0


def test_delta_comparison_detects_statistically_significant_regression():
    # Baseline ~ 4.8, Candidate ~ 3.2
    base = [4.8, 4.9, 4.7, 5.0, 4.8, 4.9, 4.8, 5.0]
    cand = [3.0, 3.2, 3.1, 3.4, 2.9, 3.1, 3.2, 3.0]
    comp = compute_delta_comparison("helpfulness", base, cand, threshold_ci_lower=-0.20)
    assert comp.regressed is True
    assert comp.delta < -1.0
    assert comp.ci_lower < -0.20
