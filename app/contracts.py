"""Load the stage contracts' reference files: the single home of every prompt and rule.

The runtime never hardcodes a prompt. It reads `stages/*/references/*.md` and `_shared/*.md`, so
what a judge reads in the repo is exactly what the model is told.
"""
from __future__ import annotations

import re
from functools import lru_cache

from .config import ROOT

SHARED = ROOT / "_shared"
STAGES = ROOT / "stages"


@lru_cache(maxsize=None)
def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def fill(template: str, **values: str) -> str:
    """Replace {name} placeholders without touching other braces (prompts contain JSON)."""
    for k, v in values.items():
        template = template.replace("{" + k + "}", v)
    return template


@lru_cache(maxsize=None)
def taxonomy() -> dict[str, dict[str, str]]:
    """intent -> {group, meaning}, parsed from _shared/intent-taxonomy.md."""
    out: dict[str, dict[str, str]] = {}
    for line in read("_shared/intent-taxonomy.md").splitlines():
        m = re.match(r"^\|\s*([a-z_]+)\s*\|\s*([A-Z]+)\s*\|\s*(.+?)\s*\|$", line)
        if m:
            out[m.group(1)] = {"group": m.group(2), "meaning": m.group(3)}
    return out


def taxonomy_block() -> str:
    return "\n".join(f"- {k}: {v['meaning']}" for k, v in taxonomy().items())


@lru_cache(maxsize=None)
def catalog_types() -> frozenset[str]:
    types = re.findall(r"^\|\s*([a-z_]+)\s*\|\s*`", read("_shared/action-catalog.md"), flags=re.M)
    return frozenset(types)


def infer_prompt(corrections_block: str = "") -> str:
    return fill(
        read("stages/02_infer-intent/references/prompt.md"),
        taxonomy=taxonomy_block(),
        corrections=corrections_block,
    )


def decide_prompt() -> str:
    return fill(
        read("stages/04_propose-decision/references/prompt.md"),
        catalog=read("_shared/action-catalog.md"),
        policies=read("_shared/policies.md"),
        voice=read("_shared/brand-voice.md"),
    )
