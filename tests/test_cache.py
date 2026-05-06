import tempfile
from pathlib import Path
from promptgate.cache import EvalCache


def test_eval_cache_storage_and_hit():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"
        cache = EvalCache(db_path=db_path)

        key, p_hash = EvalCache.compute_key(
            prompt_content="test prompt",
            input_data={"test": 123},
            model="mock-model",
            temperature=0.0,
            run_index=0
        )

        assert cache.get(key) is None

        cache.set(
            cache_key=key,
            prompt_hash=p_hash,
            model="mock-model",
            output_text="cached response text",
            prompt_tokens=10,
            completion_tokens=5,
            latency_ms=120.5,
            cost_usd=0.0001
        )

        hit = cache.get(key)
        assert hit is not None
        assert hit["output_text"] == "cached response text"
        assert hit["prompt_tokens"] == 10
        assert hit["cached"] is True

        # Test clear
        deleted = cache.clear()
        assert deleted == 1
        assert cache.get(key) is None
