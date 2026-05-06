from __future__ import annotations
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from promptgate.config import Config


class EvalCache:
    """Thread-safe SQLite-backed evaluation cache keyed by hash of (prompt_content, input, model, temperature, run_index)."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Config.CACHE_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS cache_entries (
                        cache_key TEXT PRIMARY KEY,
                        prompt_hash TEXT,
                        model TEXT,
                        output_text TEXT,
                        prompt_tokens INTEGER,
                        completion_tokens INTEGER,
                        latency_ms REAL,
                        cost_usd REAL,
                        metadata_json TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
        finally:
            conn.close()

    @staticmethod
    def compute_key(
        prompt_content: str,
        input_data: Dict[str, Any],
        model: str,
        temperature: float,
        run_index: int = 0
    ) -> Tuple[str, str]:
        """Returns (cache_key, prompt_hash)."""
        prompt_hash = hashlib.sha256(prompt_content.strip().encode("utf-8")).hexdigest()[:16]
        input_str = json.dumps(input_data, sort_keys=True, ensure_ascii=False)
        input_hash = hashlib.sha256(input_str.encode("utf-8")).hexdigest()[:16]
        
        full_key_str = f"{prompt_hash}:{input_hash}:{model}:{temperature:.2f}:{run_index}"
        cache_key = hashlib.sha256(full_key_str.encode("utf-8")).hexdigest()
        return cache_key, prompt_hash

    def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT output_text, prompt_tokens, completion_tokens, latency_ms, cost_usd, metadata_json FROM cache_entries WHERE cache_key = ?",
                (cache_key,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "output_text": row["output_text"],
                    "prompt_tokens": row["prompt_tokens"],
                    "completion_tokens": row["completion_tokens"],
                    "latency_ms": row["latency_ms"],
                    "cost_usd": row["cost_usd"],
                    "metadata": json.loads(row["metadata_json"] or "{}"),
                    "cached": True
                }
        finally:
            conn.close()
        return None

    def set(
        self,
        cache_key: str,
        prompt_hash: str,
        model: str,
        output_text: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float,
        cost_usd: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        metadata_json = json.dumps(metadata or {})
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO cache_entries 
                    (cache_key, prompt_hash, model, output_text, prompt_tokens, completion_tokens, latency_ms, cost_usd, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (cache_key, prompt_hash, model, output_text, prompt_tokens, completion_tokens, latency_ms, cost_usd, metadata_json)
                )
        finally:
            conn.close()

    def clear(self) -> int:
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM cache_entries")
                return cursor.rowcount
        finally:
            conn.close()
