"""Stage 06: execute approved actions on the simulated systems of record, undo them, audit both.

The systems of record (orders, refunds, credits, tickets, knowledge) are simulated: executing an
action computes and records its exact effect per customer, it does not call a real payment API.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from collections import Counter

from .config import settings

UNDO_SECONDS = 30

_lock = threading.Lock()
_db: sqlite3.Connection | None = None


def db() -> sqlite3.Connection:
    global _db
    if _db is None:
        state = settings.data_dir / "state"
        state.mkdir(parents=True, exist_ok=True)
        for old in state.glob("runtime-*.sqlite"):  # the demo starts clean on every boot
            try:
                old.unlink()
            except OSError:  # held by another live process (e.g. a dev server next to the tests)
                pass
        path = state / f"runtime-{os.getpid()}.sqlite"
        _db = sqlite3.connect(path, check_same_thread=False)
        _db.execute(
            "CREATE TABLE audit (id INTEGER PRIMARY KEY, session TEXT, at REAL, card TEXT, kind TEXT, digest TEXT, payload TEXT)"
        )
        _db.execute(
            "CREATE TABLE corrections (id INTEGER PRIMARY KEY, session TEXT, at REAL, card TEXT, message_id TEXT, from_intent TEXT, to_intent TEXT, reason TEXT)"
        )
    return _db


def digest(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def audit(session: str, card: str, kind: str, payload: dict) -> str:
    d = digest(payload)
    with _lock:
        db().execute(
            "INSERT INTO audit (session, at, card, kind, digest, payload) VALUES (?,?,?,?,?,?)",
            (session, time.time(), card, kind, d, json.dumps(payload, ensure_ascii=False)),
        )
        db().commit()
    return d


def record_correction(session: str, card: str, message_id: str, frm: str, to: str, reason: str) -> None:
    with _lock:
        db().execute(
            "INSERT INTO corrections (session, at, card, message_id, from_intent, to_intent, reason) VALUES (?,?,?,?,?,?,?)",
            (session, time.time(), card, message_id, frm, to, reason),
        )
        db().commit()


def log(session: str, limit: int = 30) -> list[dict]:
    with _lock:
        rows = db().execute(
            "SELECT at, card, kind, digest, payload FROM audit WHERE session=? ORDER BY id DESC LIMIT ?", (session, limit)
        ).fetchall()
    return [{"at": r[0], "card": r[1], "kind": r[2], "digest": r[3], "payload": json.loads(r[4])} for r in rows]


def execute(decision: dict, member_ids: list[str], msgs: dict, infs: dict, contacts: dict) -> dict:
    """Compute the effect of every action on the card. Returns the execution record."""
    custs: dict[str, str] = {}  # contact -> language
    for i in member_ids[:300]:
        custs.setdefault(msgs[i]["contact_id"], infs[i]["language"])
    effects: dict = {"replies": Counter(), "refund_sar": 0, "credit_sar": 0, "reships": 0, "tickets": [], "knowledge": None, "tags": None, "vip_followups": 0}
    for a in decision["actions"]:
        t, p = a["type"], a.get("params", {})
        if t == "send_reply_batch":
            for lang in custs.values():
                effects["replies"][lang if lang in ("en", "ar") or lang in decision.get("reply_other", {}) else "en"] += 1
        elif t == "issue_refund":
            each = float(p.get("amount_sar_each", 0))
            for c in custs:
                orders = contacts.get(c, {}).get("orders") or [{"amount_sar": each}]
                effects["refund_sar"] += min(each, float(orders[0]["amount_sar"]))
        elif t == "issue_credit":
            effects["credit_sar"] += float(p.get("amount_sar_each", 0)) * len(custs)
        elif t == "reship_item":
            effects["reships"] += len(custs)
        elif t == "escalate_to_team":
            effects["tickets"].append({"team": p.get("team", "tech"), "id": f"TCK-{int(time.time() * 1000) % 1_000_000:06d}"})
        elif t == "update_knowledge":
            effects["knowledge"] = {"title": p.get("title") or decision["hypothesis"]}
        elif t == "tag_conversations":
            effects["tags"] = p.get("label") or decision["hypothesis"]
    effects["vip_followups"] = sum(contacts.get(c, {}).get("tier") == "vip" for c in custs)
    effects["refund_sar"] = round(effects["refund_sar"])
    effects["credit_sar"] = round(effects["credit_sar"])
    effects["replies"] = dict(effects["replies"])
    return {"at": time.time(), "undo_until": time.time() + UNDO_SECONDS, "customers": len(custs), "effects": effects}
