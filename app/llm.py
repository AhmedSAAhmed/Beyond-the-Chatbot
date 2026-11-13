"""LLM client.

One job: turn a (system, user) prompt into a validated JSON object.

- A pool of (provider, model) pairs, Groq first (fast), then Gemini; a rate-limited model cools down
  and the next one answers. Both are called over plain HTTPS with httpx,
  so there is no vendor SDK to pin.
- Every successful JSON call is cached on disk by a hash of (model, system, user). Replays of the
  same prompt cost nothing, and the offline pipeline can be re-run without re-billing.
- Customer text is always passed inside the *user* turn as data, never in the system prompt.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from .config import settings

log = logging.getLogger("llm")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:{verb}"


from collections import Counter

usage: Counter = Counter()  # provider -> successful calls (shown on /how)


class LLMError(RuntimeError):
    """Raised when every provider failed for one call."""


def _cache_path(kind: str, key: str) -> Path:
    d = settings.cache_dir / kind
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}.json"


def _key(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{") :]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start : end + 1])


DEFAULT_POOL = (
    "groq:openai/gpt-oss-120b,gemini:gemini-3.5-flash-lite,groq:qwen/qwen3.8-27b,"
    "gemini:gemini-2.5-flash,gemini:gemini-3.1-flash-lite,gemini:gemini-flash-lite-latest,"
    "groq:openai/gpt-oss-20b,gemini:gemini-3.5-flash"
)
_cooldown: dict[str, float] = {}
_cool_lock = threading.Lock()


def pool() -> list[tuple[str, str]]:
    """(provider, model) pairs in preference order. Each model has its own free-tier quota."""
    out = []
    for item in os.getenv("LLM_POOL", DEFAULT_POOL).split(","):
        prov, _, model = item.strip().partition(":")
        if (prov == "groq" and settings.groq_api_key) or (prov == "gemini" and settings.gemini_api_key):
            out.append((prov, model))
    return out


class _RateLimited(Exception):
    def __init__(self, wait: float):
        self.wait = wait


def _groq(model: str, system: str, user: str, temperature: float, timeout: float) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if model.startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"
    elif model.startswith("qwen/"):
        body["reasoning_format"] = "hidden"
    r = httpx.post(GROQ_URL, json=body, headers={"Authorization": f"Bearer {settings.groq_api_key}"}, timeout=timeout)
    if r.status_code == 429:
        raise _RateLimited(float(r.headers.get("retry-after", "20") or 20))
    r.raise_for_status()
    return _parse_json(r.json()["choices"][0]["message"]["content"])


def _gemini(model: str, system: str, user: str, temperature: float, timeout: float) -> dict[str, Any]:
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    r = httpx.post(GEMINI_URL.format(model=model, verb="generateContent"), headers={"x-goog-api-key": settings.gemini_api_key}, json=body, timeout=timeout)
    if r.status_code == 429:
        raise _RateLimited(40)
    r.raise_for_status()
    parts = r.json()["candidates"][0]["content"]["parts"]
    return _parse_json("".join(p.get("text", "") for p in parts if not p.get("thought")))


CALL = {"groq": _groq, "gemini": _gemini}


def complete_json(
    system: str,
    user: str,
    *,
    temperature: float = 0.1,
    timeout: float = 45.0,
    use_cache: bool = True,
    deadline: float = 240.0,
) -> dict[str, Any]:
    """Return a JSON object from the first model in the pool that answers. Raises LLMError.

    A model that returns 429 cools down and the next one is tried at once, so a burst of work
    spreads across every free quota instead of waiting on one.
    """
    path = _cache_path("json", _key("v1", system, user))
    if use_cache and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    models = pool()
    if not models:
        raise LLMError("no LLM provider configured (set GROQ_API_KEY or GEMINI_API_KEY)")
    errors: list[str] = []
    failures: dict[str, int] = {}
    stop = time.time() + deadline
    while time.time() < stop:
        now = time.time()
        with _cool_lock:
            ready = [(p, m) for p, m in models if _cooldown.get(m, 0) <= now and failures.get(m, 0) < 2]
        if not ready:
            with _cool_lock:
                waits = [_cooldown.get(m, 0) - now for _, m in models if failures.get(m, 0) < 2]
            if not waits:
                break
            time.sleep(min(max(min(waits), 0.5), 15))
            continue
        prov, model = ready[0]
        try:
            out = CALL[prov](model, system, user, temperature, timeout)
            usage[f"{prov}:{model}"] += 1
            path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
            return out
        except _RateLimited as rl:
            with _cool_lock:
                _cooldown[model] = time.time() + min(rl.wait, 90)
            errors.append(f"{model}: rate limited")
        except (httpx.HTTPError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
            failures[model] = failures.get(model, 0) + 1
            errors.append(f"{model}: {type(exc).__name__}: {str(exc)[:160]}")
            log.warning("model %s failed: %s", model, errors[-1])
    raise LLMError("; ".join(errors[-4:]) or "deadline reached")
