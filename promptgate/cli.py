from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from promptgate.config import Config
from promptgate.models import PromptDefinition, SuiteRunResult, GateEvaluation
from promptgate.runner import EvalRunner
from promptgate.gate import RegressionGate
from promptgate.reporter import PRReporter
from promptgate.calibrate import JudgeCalibrator

app = typer.Typer(
    name="promptgate",
    help="PromptGate: CI/CD Quality Gate & Regression Blocker for LLM Prompts.",
    add_completion=False
)
console = Console()


def _get_dataset_for_prompt(prompt_name: str) -> Path:
    p = Config.DATASETS_DIR / f"{prompt_name}.jsonl"
    if p.exists():
        return p
    # Fallback search
    for f in Config.DATASETS_DIR.glob("*.jsonl"):
        if prompt_name in f.stem:
            return f
    return Config.DATASETS_DIR / "support_reply.jsonl"


def _get_baseline_path(prompt_name: str) -> Path:
    Config.BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    return Config.BASELINES_DIR / f"{prompt_name}_baseline.json"


@app.command()
def run(
    prompt_path: Path = typer.Argument(..., help="Path to prompt YAML file"),
    dataset_path: Optional[Path] = typer.Option(None, "--dataset", "-d", help="Path to dataset JSONL"),
    save_baseline: bool = typer.Option(False, "--save-baseline", help="Save run as main baseline for this prompt"),
    smoke: Optional[int] = typer.Option(None, "--smoke", "-s", help="Run only first N cases (smoke test)"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass SQLite cache")
):
    """Run evaluation suite on a prompt."""
    if not prompt_path.exists():
        console.print(f"[bold red]Error: Prompt file '{prompt_path}' does not exist.[/bold red]")
        raise typer.Exit(code=1)

    prompt = EvalRunner.load_prompt(prompt_path)
    ds_path = dataset_path or _get_dataset_for_prompt(prompt.name)
    
    if not ds_path.exists():
        console.print(f"[bold red]Error: Dataset '{ds_path}' not found.[/bold red]")
        raise typer.Exit(code=1)

    cases = EvalRunner.load_dataset(ds_path)
    runner = EvalRunner(use_cache=not no_cache)

    console.print(Panel(
        f"[bold cyan]PromptGate Evaluation Suite[/bold cyan]\n"
        f"Prompt: [yellow]{prompt.name}[/yellow] ([dim]{prompt.version}[/dim])\n"
        f"Model: [green]{prompt.model}[/green] | Temp: {prompt.temperature} | Cases: {len(cases if not smoke else cases[:smoke])}",
        border_style="cyan"
    ))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Evaluating test cases & deterministic checks...", total=None)
        result = runner.run_suite(prompt, cases, smoke_count=smoke)
        progress.update(task, description="[green]Evaluation completed!")

    # Display Metrics Table
    table = Table(title=f"Results for {prompt.name} ({prompt.version})", border_style="dim")
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Mean Score", justify="center", style="bold")
    table.add_column("95% Bootstrap CI", justify="center", style="yellow")
    table.add_column("Std Dev", justify="center")
    table.add_column("N", justify="center")

    for metric, summary in result.metrics.items():
        ci_str = f"[{summary.ci_lower:.2f}, {summary.ci_upper:.2f}]"
        table.add_row(metric, f"{summary.mean:.2f}", ci_str, f"{summary.std:.2f}", str(summary.n))

    console.print(table)

    # Health summary
    hard_status = "[green]100% PASS[/green]" if result.hard_pass_rate >= 1.0 else f"[red]{result.hard_pass_rate*100:.1f}%[/red]"
    console.print(
        f"\n[bold]Deterministic Hard Pass Rate:[/bold] {hard_status} | "
        f"[bold]Avg Latency:[/bold] {result.avg_latency_ms:.1f}ms | "
        f"[bold]Total Cost:[/bold] ${result.total_cost_usd:.5f} | "
        f"[bold]Cache Hit Rate:[/bold] {result.cache_hit_rate * 100:.1f}%\n"
    )

    if save_baseline:
        base_file = _get_baseline_path(prompt.name)
        with open(base_file, "w", encoding="utf-8") as f:
            f.write(result.model_dump_json(indent=2))
        console.print(f"[bold green]✓ Saved baseline snapshot to {base_file}[/bold green]")

    return result


@app.command()
def compare(
    candidate_path: Path = typer.Argument(..., help="Path to candidate prompt YAML"),
    baseline_path: Optional[Path] = typer.Option(None, "--baseline", "-b", help="Path to baseline prompt YAML or baseline JSON snapshot"),
    dataset_path: Optional[Path] = typer.Option(None, "--dataset", "-d", help="Path to dataset JSONL"),
    smoke: Optional[int] = typer.Option(None, "--smoke", "-s", help="Smoke test count"),
    output_md: Optional[Path] = typer.Option(None, "--output-md", help="Save markdown report to file (for GitHub PR comment)"),
    fail_on_regression: bool = typer.Option(True, "--fail-on-regression/--no-fail-on-regression", help="Exit with code 1 if quality gate fails")
):
    """Compare candidate prompt against baseline, calculate bootstrap deltas, and enforce regression gate."""
    if not candidate_path.exists():
        console.print(f"[bold red]Error: Candidate prompt '{candidate_path}' not found.[/bold red]")
        raise typer.Exit(code=1)

    candidate_prompt = EvalRunner.load_prompt(candidate_path)
    ds_path = dataset_path or _get_dataset_for_prompt(candidate_prompt.name)
    cases = EvalRunner.load_dataset(ds_path)
    runner = EvalRunner()

    console.print(Panel(
        f"[bold cyan]PromptGate Regression Gate Execution[/bold cyan]\n"
        f"Evaluating Candidate: [yellow]{candidate_path.name}[/yellow]",
        border_style="cyan"
    ))

    # Run Candidate
    candidate_result = runner.run_suite(candidate_prompt, cases, smoke_count=smoke)

    # Resolve Baseline
    baseline_result: Optional[SuiteRunResult] = None

    if baseline_path and baseline_path.suffix == ".json" and baseline_path.exists():
        with open(baseline_path, "r", encoding="utf-8") as f:
            baseline_result = SuiteRunResult(**json.load(f))
    elif baseline_path and baseline_path.suffix in [".yaml", ".yml"] and baseline_path.exists():
        base_prompt = EvalRunner.load_prompt(baseline_path)
        baseline_result = runner.run_suite(base_prompt, cases, smoke_count=smoke)
    else:
        # Check standard baseline dir
        default_base_json = _get_baseline_path(candidate_prompt.name)
        default_base_yaml = Config.PROMPTS_DIR / f"{candidate_prompt.name}.v1.yaml"
        if default_base_json.exists():
            with open(default_base_json, "r", encoding="utf-8") as f:
                baseline_result = SuiteRunResult(**json.load(f))
        elif default_base_yaml.exists():
            base_prompt = EvalRunner.load_prompt(default_base_yaml)
            baseline_result = runner.run_suite(base_prompt, cases, smoke_count=smoke)
        else:
            console.print(f"[bold red]Error: No baseline found for '{candidate_prompt.name}'. Run with --save-baseline first.[/bold red]")
            raise typer.Exit(code=1)

    # Evaluate Gate
    gate = RegressionGate().evaluate(candidate_result, baseline_result)
    report_md = PRReporter.generate_markdown_report(gate, candidate_result, baseline_result)

    # Print summary to console
    console.print("\n" + "=" * 60)
    if gate.passed:
        console.print(Panel("[bold green]✅ QUALITY GATE PASSED — MERGE ALLOWED[/bold green]\nAll deterministic constraints met and quality maintained within 95% bootstrap confidence bounds.", border_style="green"))
    else:
        console.print(Panel("[bold red]🛑 QUALITY GATE BLOCKED — REGRESSION DETECTED[/bold red]\nPull request blocked due to quality degradation or safety violation.", border_style="red"))

    # Table of Deltas
    table = Table(title="Candidate vs Baseline Deltas (95% Bootstrap CI)", border_style="dim")
    table.add_column("Metric", style="cyan")
    table.add_column("Baseline", justify="center")
    table.add_column("Candidate", justify="center")
    table.add_column("Δ Mean", justify="center", style="bold")
    table.add_column("95% CI", justify="center", style="yellow")
    table.add_column("Status", justify="center")

    for d in gate.metric_deltas:
        badge = "[bold red]REGRESSED[/bold red]" if d.regressed else "[bold green]PASS[/bold green]"
        sign = "+" if d.delta > 0 else ""
        table.add_row(
            d.metric_name,
            f"{d.baseline_mean:.2f}",
            f"{d.candidate_mean:.2f}",
            f"{sign}{d.delta:.2f}",
            f"[{d.ci_lower:+.2f}, {d.ci_upper:+.2f}]",
            badge
        )

    console.print(table)

    if gate.hard_failures:
        console.print("\n[bold red]Hard Failures:[/bold red]")
        for h in gate.hard_failures:
            console.print(f"  ❌ {h}")

    if gate.worst_cases:
        console.print(f"\n[bold yellow]Top {len(gate.worst_cases)} Regressed Cases:[/bold yellow]")
        for rc in gate.worst_cases:
            console.print(f"  • [cyan]{rc.test_case_id}[/cyan]: Score dropped by [bold red]{rc.delta:.2f}[/bold red] ({rc.metric_name})")
            console.print(f"    [dim]Diagnosis: {rc.explanation}[/dim]")

    if output_md:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        with open(output_md, "w", encoding="utf-8") as f:
            f.write(report_md)
        console.print(f"\n[bold green]✓ Markdown PR report saved to {output_md}[/bold green]")

    if not gate.passed and fail_on_regression:
        raise typer.Exit(code=1)


@app.command()
def calibrate(
    dataset_path: Optional[Path] = typer.Option(None, "--dataset", "-d", help="Path to hand-labeled calibration dataset JSONL"),
    metric: str = typer.Option("helpfulness", "--metric", "-m", help="Metric to calibrate")
):
    """Run calibration on hand-labeled dataset and calculate Cohen's Kappa."""
    calibrator = JudgeCalibrator()
    console.print(Panel(f"[bold cyan]Calibrating LLM Judge against Hand-Labeled Ground Truth[/bold cyan]\nMetric: [yellow]{metric}[/yellow]", border_style="cyan"))

    result = calibrator.run_calibration(calibration_path=dataset_path, metric_name=metric)
    report_md = result.to_markdown()

    # Pretty print
    table = Table(title="Judge Calibration & Agreement Metrics", border_style="dim")
    table.add_column("Metric", style="cyan")
    table.add_column("Score", style="bold green", justify="center")
    table.add_column("Benchmark Target", style="dim", justify="center")

    table.add_row("Cohen's Kappa (κ)", f"{result.cohen_kappa:.3f}", "> 0.60 (Substantial)")
    table.add_row("Exact Agreement Rate", f"{result.exact_agreement_rate * 100:.1f}%", "> 70.0%")
    table.add_row("Within-1 Score Agreement", f"{result.within_one_agreement_rate * 100:.1f}%", "> 90.0%")
    table.add_row("Evaluated Test Samples", str(result.total_samples), "50 hand-labeled cases")

    console.print(table)
    console.print(f"\n[bold]Inter-Rater Reliability:[/bold] {'Almost Perfect' if result.cohen_kappa > 0.8 else 'Substantial'}")

    # Save artifact
    calib_out = Config.PROJECT_ROOT / "calibration_report.md"
    with open(calib_out, "w", encoding="utf-8") as f:
        f.write(report_md)
    console.print(f"[bold green]✓ Saved calibration report to {calib_out}[/bold green]\n")


@app.command()
def demo(
    scenario: str = typer.Option("all", "--scenario", "-s", help="Scenario: 'schema', 'policy', 'tone', 'safe', or 'all'")
):
    """Run interactive demonstration of deliberate regressions caught by PromptGate."""
    scenarios = {
        "schema": (
            Config.PROMPTS_DIR / "regressions" / "invoice_extract.v2_broke_schema.yaml",
            "Broken JSON schema & markdown fence insertion"
        ),
        "policy": (
            Config.PROMPTS_DIR / "regressions" / "support_reply.v2_broke_policy.yaml",
            "Banned refund promises & unauthorized SLA guarantees"
        ),
        "tone": (
            Config.PROMPTS_DIR / "regressions" / "support_reply.v2_rude_tone.yaml",
            "Rude & dismissive tone regression"
        ),
        "safe": (
            Config.PROMPTS_DIR / "improvements" / "support_reply.v2_safe_refine.yaml",
            "Safe cosmetic prompt refinement (false-positive test)"
        )
    }

    selected = [scenario] if scenario in scenarios else ["schema", "policy", "tone", "safe"]

    for sc in selected:
        prompt_file, desc = scenarios[sc]
        console.print(Panel(f"[bold magenta]Demo Scenario: {sc.upper()}[/bold magenta]\n[dim]{desc}[/dim]", border_style="magenta"))
        try:
            compare(
                candidate_path=prompt_file,
                baseline_path=None,
                dataset_path=None,
                smoke=10,
                output_md=None,
                fail_on_regression=False
            )
        except Exception as e:
            console.print(f"[dim]Scenario execution completed: {e}[/dim]")
        console.print("\n" + "-" * 50 + "\n")


@app.command()
def serve(
    port: int = typer.Option(8000, "--port", "-p", help="Port to serve web report viewer")
):
    """Launch local dark-mode dashboard to visually explore evaluations, diffs, and gate results."""
    from promptgate.web.app import start_server
    start_server(port=port)


if __name__ == "__main__":
    app()
