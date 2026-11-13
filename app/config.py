"""Runtime settings, read once from the environment (and a local .env in development)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:  # .env is a local convenience only; Render injects real env vars.
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
except ImportError:  # pragma: no cover
    pass


def _clean(value: str | None) -> str:
    return (value or "").strip().strip('"').strip("'")


@dataclass(frozen=True)
class Settings:
    groq_api_key: str = _clean(os.getenv("GROQ_API_KEY"))
    gemini_api_key: str = _clean(os.getenv("GEMINI_API_KEY"))
    groq_model: str = _clean(os.getenv("GROQ_MODEL")) or "openai/gpt-oss-120b"
    gemini_model: str = _clean(os.getenv("GEMINI_MODEL")) or "gemini-3.5-flash"
    replay_seconds: float = float(os.getenv("REPLAY_SECONDS", "6"))
    max_sessions: int = int(os.getenv("MAX_SESSIONS", "300"))
    inject_per_hour: int = int(os.getenv("INJECT_PER_HOUR", "40"))
    data_dir: Path = ROOT / "data"
    cache_dir: Path = ROOT / "data" / "cache"

    @property
    def live_llm(self) -> bool:
        return bool(self.groq_api_key or self.gemini_api_key)


settings = Settings()
