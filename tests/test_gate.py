from promptgate.runner import EvalRunner
from promptgate.gate import RegressionGate
from promptgate.config import Config


def test_regression_gate_detects_deliberate_policy_regression():
    runner = EvalRunner(use_cache=False)
    
    baseline_prompt = EvalRunner.load_prompt(Config.PROMPTS_DIR / "support_reply.v1.yaml")
    regressed_prompt = EvalRunner.load_prompt(Config.PROMPTS_DIR / "regressions" / "support_reply.v2_broke_policy.yaml")
    
    cases = EvalRunner.load_dataset(Config.DATASETS_DIR / "support_reply.jsonl")[:5]

    base_result = runner.run_suite(baseline_prompt, cases)
    cand_result = runner.run_suite(regressed_prompt, cases)

    gate = RegressionGate().evaluate(cand_result, base_result)
    
    # Gate should block the PR!
    assert gate.passed is False
    assert len(gate.hard_failures) > 0 or any(d.regressed for d in gate.metric_deltas)


def test_regression_gate_passes_safe_refinement():
    runner = EvalRunner(use_cache=False)
    
    baseline_prompt = EvalRunner.load_prompt(Config.PROMPTS_DIR / "support_reply.v1.yaml")
    safe_prompt = EvalRunner.load_prompt(Config.PROMPTS_DIR / "improvements" / "support_reply.v2_safe_refine.yaml")
    
    cases = EvalRunner.load_dataset(Config.DATASETS_DIR / "support_reply.jsonl")[:5]

    base_result = runner.run_suite(baseline_prompt, cases)
    cand_result = runner.run_suite(safe_prompt, cases)

    gate = RegressionGate().evaluate(cand_result, base_result)
    
    # Safe refinement must PASS (no false-positive block!)
    assert gate.passed is True
    assert len(gate.hard_failures) == 0
