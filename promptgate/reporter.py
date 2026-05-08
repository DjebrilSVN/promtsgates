from __future__ import annotations
from typing import Optional
from promptgate.models import GateEvaluation, SuiteRunResult


class PRReporter:
    """Generates GitHub PR bot markdown comments and terminal summaries."""

    @staticmethod
    def generate_markdown_report(
        gate: GateEvaluation,
        candidate_result: SuiteRunResult,
        baseline_result: SuiteRunResult
    ) -> str:
        status_icon = "✅" if gate.passed else "🛑"
        status_title = (
            "PromptGate Eval Passed — Merge Allowed"
            if gate.passed
            else "PromptGate Blocked — Quality Regression Detected"
        )

        md = []
        md.append(f"## {status_icon} PromptGate Quality Gate: {status_title}\n")
        md.append(
            f"**Prompt:** `{gate.prompt_name}` | "
            f"**Candidate:** `{gate.candidate_version}` (`{candidate_result.prompt_hash[:8]}`) | "
            f"**Baseline:** `{gate.baseline_version}` (`{baseline_result.prompt_hash[:8]}`)\n"
        )

        if not gate.passed:
            md.append("> ⚠️ **Regression Alert:** This pull request introduces statistically meaningful quality regressions or breaches deterministic safety/schema constraints. The CI check has failed to protect production.\n")

        # Hard failures section
        if gate.hard_failures:
            md.append("### 🚨 Hard Rule Failures")
            for fail in gate.hard_failures:
                md.append(f"- ❌ **{fail}**")
            md.append("")

        # Metrics Delta Table
        md.append("### 📊 Metric Evaluation & Bootstrap Confidence Intervals (95% CI)")
        md.append("| Metric | Baseline (μ) | Candidate (μ) | Δ Mean | 95% Bootstrap CI | Status |")
        md.append("| :--- | :---: | :---: | :---: | :---: | :---: |")

        for d in gate.metric_deltas:
            status_badge = "❌ REGRESSED" if d.regressed else "✅ PASS"
            sign = "+" if d.delta > 0 else ""
            delta_str = f"{sign}{d.delta:.2f}"
            ci_str = f"[{d.ci_lower:+.2f}, {d.ci_upper:+.2f}]"
            md.append(
                f"| **{d.metric_name}** | {d.baseline_mean:.2f} | {d.candidate_mean:.2f} | "
                f"`{delta_str}` | `{ci_str}` | {status_badge} |"
            )
        md.append("")

        # Performance & Cost Table
        cost_delta = candidate_result.total_cost_usd - baseline_result.total_cost_usd
        lat_delta = candidate_result.avg_latency_ms - baseline_result.avg_latency_ms
        hard_pass_delta = (candidate_result.hard_pass_rate - baseline_result.hard_pass_rate) * 100

        md.append("### ⚡ Performance, Cost & Deterministic Health")
        md.append("| Metric | Baseline | Candidate | Delta |")
        md.append("| :--- | :---: | :---: | :---: |")
        md.append(f"| **Deterministic Hard Pass Rate** | {baseline_result.hard_pass_rate * 100:.1f}% | {candidate_result.hard_pass_rate * 100:.1f}% | `{hard_pass_delta:+.1f}%` |")
        md.append(f"| **Avg Latency** | {baseline_result.avg_latency_ms:.1f}ms | {candidate_result.avg_latency_ms:.1f}ms | `{lat_delta:+.1f}ms` |")
        md.append(f"| **Run Cost (USD)** | ${baseline_result.total_cost_usd:.5f} | ${candidate_result.total_cost_usd:.5f} | `${cost_delta:+.5f}` |")
        md.append(f"| **Cache Hit Rate** | {baseline_result.cache_hit_rate * 100:.1f}% | {candidate_result.cache_hit_rate * 100:.1f}% | — |")
        md.append("")

        # Worst 5 Regressed Cases
        if gate.worst_cases:
            md.append("### 🔍 Top Regressed Cases (Side-by-Side Review)")
            md.append("Here are the test cases where the candidate model output showed the steepest quality decline:")
            md.append("")
            
            for i, rc in enumerate(gate.worst_cases, 1):
                md.append(f"<details><summary><b>Case #{i} ({rc.test_case_id})</b> — Metric: <code>{rc.metric_name}</code> (Score: {rc.baseline_score} ➔ {rc.candidate_score}, Δ: {rc.delta:+.2f})</summary>\n")
                md.append(f"**Input:**\n```\n{rc.input_preview}\n```\n")
                md.append(f"**Judge Diagnosis:** *\"{rc.explanation}\"*\n")
                md.append("| Baseline Output | Candidate Output |")
                md.append("| :--- | :--- |")
                
                # Sanitize newlines for markdown table
                b_clean = rc.baseline_output.replace("\n", "<br>")
                c_clean = rc.candidate_output.replace("\n", "<br>")
                if len(b_clean) > 400:
                    b_clean = b_clean[:397] + "..."
                if len(c_clean) > 400:
                    c_clean = c_clean[:397] + "..."

                md.append(f"| {b_clean} | {c_clean} |")
                md.append("\n</details>\n")

        # Actionable recommendations
        if not gate.passed:
            md.append("### 🛠️ Remediation Guidance")
            md.append("1. **Review Failed Cases**: Inspect the side-by-side diffs above to see specifically what prompt instruction changed behavior.")
            md.append("2. **Fix Policy & Schema Directives**: Ensure explicit constraints (e.g. JSON format, banned promise guardrails) are reinforced in the system prompt.")
            md.append("3. **Re-run Locally**: Run `promptgate compare` locally to verify changes before pushing.")
            md.append("")

        md.append("\n---\n*Report generated automatically by [PromptGate](https://github.com/DjebrilSVN/PromptGate) CI/CD pipeline.*")
        return "\n".join(md)
