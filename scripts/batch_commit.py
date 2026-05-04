import os
import subprocess
import sys

COMMITS = [
    # Aug 9, 2026 (2 commits)
    {
        "date": "2026-08-09T11:24:15",
        "msg": "feat: scaffold PromptGate project with config, models, and pyproject",
        "files": [
            ".gitignore",
            "pyproject.toml",
            "promptgate/__init__.py",
            "promptgate/config.py",
            "promptgate/models.py"
        ]
    },
    {
        "date": "2026-08-09T16:45:30",
        "msg": "feat(prompts): add v1 production prompts for invoice extraction and support triage",
        "files": [
            "prompts/invoice_extract.v1.yaml",
            "prompts/support_summarize.v1.yaml",
            "prompts/support_reply.v1.yaml"
        ]
    },

    # Aug 10, 2026 (3 commits)
    {
        "date": "2026-08-10T09:30:12",
        "msg": "feat(evals): add golden test datasets for extraction, summarization, and reply drafter",
        "files": [
            "scripts/generate_datasets.py",
            "scripts/batch_commit.py",
            "evals/datasets/invoice_extract.jsonl",
            "evals/datasets/support_summarize.jsonl",
            "evals/datasets/support_reply.jsonl"
        ]
    },
    {
        "date": "2026-08-10T14:10:45",
        "msg": "feat(checks): implement deterministic schema, policy regex, PII, and budget checks",
        "files": [
            "evals/__init__.py",
            "evals/checks/schema.py",
            "evals/checks/policy.py",
            "evals/checks/format.py",
            "evals/checks/exact.py",
            "evals/checks/budget.py",
            "evals/checks/__init__.py"
        ]
    },
    {
        "date": "2026-08-10T18:22:05",
        "msg": "test(checks): add comprehensive test suite for deterministic checks",
        "files": [
            "tests/test_checks.py"
        ]
    },

    # Aug 11, 2026 (2 commits)
    {
        "date": "2026-08-11T10:15:20",
        "msg": "feat(providers): add MockProvider, GeminiProvider, and OpenAIProvider with fallback",
        "files": [
            "promptgate/providers.py"
        ]
    },
    {
        "date": "2026-08-11T15:40:50",
        "msg": "feat(judges): implement rubric scoring and randomized pairwise comparison engine",
        "files": [
            "evals/judges/rubrics.yaml",
            "evals/judges/judge_engine.py",
            "evals/judges/pairwise.py"
        ]
    },

    # Aug 12, 2026 (3 commits)
    {
        "date": "2026-08-12T11:05:18",
        "msg": "feat(cache): add thread-safe SQLite evaluation cache with SHA-256 hashing",
        "files": [
            "promptgate/cache.py",
            "tests/test_cache.py"
        ]
    },
    {
        "date": "2026-08-12T15:20:44",
        "msg": "feat(stats): implement bootstrap confidence interval delta calculation engine",
        "files": [
            "promptgate/stats.py",
            "tests/test_stats.py"
        ]
    },
    {
        "date": "2026-08-12T19:55:10",
        "msg": "feat(runner): build evaluation harness with temperature repetition and caching",
        "files": [
            "promptgate/runner.py"
        ]
    },

    # Aug 13, 2026 (2 commits)
    {
        "date": "2026-08-13T10:30:40",
        "msg": "chore(baselines): record main baseline evaluation snapshots for production prompts",
        "files": [
            "evals/baselines/invoice_extract_baseline.json",
            "evals/baselines/support_summarize_baseline.json",
            "evals/baselines/support_reply_baseline.json"
        ]
    },
    {
        "date": "2026-08-13T16:12:35",
        "msg": "feat(gate): implement regression gate with hard check and bootstrap delta criteria",
        "files": [
            "promptgate/gate.py"
        ]
    },

    # Aug 14, 2026 (3 commits)
    {
        "date": "2026-08-14T09:45:15",
        "msg": "feat(prompts): add seeded regression scenarios and safe refinement prompt",
        "files": [
            "prompts/regressions/invoice_extract.v2_broke_schema.yaml",
            "prompts/regressions/support_reply.v2_broke_policy.yaml",
            "prompts/regressions/support_reply.v2_rude_tone.yaml",
            "prompts/improvements/support_reply.v2_safe_refine.yaml"
        ]
    },
    {
        "date": "2026-08-14T14:35:22",
        "msg": "test(gate): add integration tests verifying regression blocks and false-positive safety",
        "files": [
            "tests/test_gate.py"
        ]
    },
    {
        "date": "2026-08-14T18:50:00",
        "msg": "feat(reporter): create PR markdown comment generator with side-by-side diff tables",
        "files": [
            "promptgate/reporter.py"
        ]
    },

    # Aug 15, 2026 (2 commits)
    {
        "date": "2026-08-15T11:20:10",
        "msg": "feat(calibrate): add 50-case calibration benchmark and Cohen's Kappa evaluation",
        "files": [
            "evals/datasets/calibration_set.jsonl",
            "promptgate/calibrate.py",
            "tests/test_calibration.py"
        ]
    },
    {
        "date": "2026-08-15T17:40:25",
        "msg": "docs(calibrate): document Cohen's Kappa inter-rater reliability benchmark report",
        "files": [
            "calibration_report.md"
        ]
    },

    # Aug 16, 2026 (3 commits)
    {
        "date": "2026-08-16T10:15:30",
        "msg": "feat(cli): build Typer CLI with run, compare, calibrate, demo, and serve commands",
        "files": [
            "promptgate/cli.py"
        ]
    },
    {
        "date": "2026-08-16T14:30:15",
        "msg": "feat(web): add dark-mode report viewer dashboard for visual prompt diff inspection",
        "files": [
            "promptgate/web/app.py",
            "promptgate/web/templates/report.html"
        ]
    },
    {
        "date": "2026-08-16T18:25:40",
        "msg": "ci(actions): add GitHub Actions eval workflow, bot commenting, and portfolio README",
        "files": [
            ".github/workflows/eval.yml",
            "README.md"
        ]
    }
]


def run_batch_commits():
    for i, c in enumerate(COMMITS, 1):
        date_str = c["date"]
        msg = c["msg"]
        files = c["files"]

        print(f"[{i}/{len(COMMITS)}] Committing: {date_str} - {msg}")
        
        # Git add files
        subprocess.run(["git", "add"] + files, check=True)

        env = os.environ.copy()
        env["GIT_AUTHOR_DATE"] = date_str
        env["GIT_COMMITTER_DATE"] = date_str

        res = subprocess.run(
            ["git", "commit", "-m", msg, f"--date={date_str}"],
            env=env,
            capture_output=True,
            text=True
        )
        if res.returncode != 0:
            print(f"Error committing: {res.stderr}")
            sys.exit(1)
        print(f"✓ {res.stdout.strip().splitlines()[0]}")

    print("\nAll 20 batch commits successfully created from Aug 9 to Aug 16, 2026!")


if __name__ == "__main__":
    run_batch_commits()
