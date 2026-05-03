from __future__ import annotations
import os
from pathlib import Path
from pydantic import BaseModel, Field

class GateThresholds(BaseModel):
    min_hard_pass_rate: float = 1.0  # 100% hard checks must pass (schema, safety, banned phrases)
    max_allowable_drop_ci_lower: float = -0.20  # Score lower bound delta threshold
    significance_level_p: float = 0.05
    min_pass_rate_delta: float = 0.0  # Hard pass rate cannot decrease
    n_bootstrap_samples: int = 1000

class Config:
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
    PROMPTS_DIR: Path = PROJECT_ROOT / "prompts"
    DATASETS_DIR: Path = PROJECT_ROOT / "evals" / "datasets"
    CHECKS_DIR: Path = PROJECT_ROOT / "evals" / "checks"
    JUDGES_DIR: Path = PROJECT_ROOT / "evals" / "judges"
    BASELINES_DIR: Path = PROJECT_ROOT / "evals" / "baselines"
    CACHE_DIR: Path = PROJECT_ROOT / "evals" / "cache"
    CACHE_DB_PATH: Path = CACHE_DIR / "promptgate_cache.db"

    # API Keys from environment
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Provider Models
    DEFAULT_TEST_MODEL: str = os.getenv("PROMPTGATE_TEST_MODEL", "gemini-2.5-flash")
    DEFAULT_JUDGE_MODEL: str = os.getenv("PROMPTGATE_JUDGE_MODEL", "gemini-2.5-pro")

    # Repetitions per test case at production temperature
    DEFAULT_REPETITIONS: int = int(os.getenv("PROMPTGATE_RUN_REPETITIONS", "3"))

    # Gate thresholds
    THRESHOLDS: GateThresholds = GateThresholds()

    # Costs per 1K tokens ($ USD) for tracking
    MODEL_COSTS: dict = {
        "gemini-2.5-flash": {"prompt": 0.000075, "completion": 0.0003},
        "gemini-2.5-pro": {"prompt": 0.00125, "completion": 0.005},
        "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
        "gpt-4o": {"prompt": 0.0025, "completion": 0.010},
        "mock-test-model": {"prompt": 0.00001, "completion": 0.00002},
        "mock-judge-model": {"prompt": 0.00005, "completion": 0.0001},
    }
