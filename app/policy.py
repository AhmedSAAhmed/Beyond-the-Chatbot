"""The policy gate (stage 04 + 06). Code, not prompt, decides what an action may do.

Every change the gate makes is written to `policy_notes`, so the person sees what was adjusted.
"""
from __future__ import annotations

import copy
from typing import Any

from . import contracts

REFUND_CAP = 500
CREDIT_CAP = 100
MAX_BATCH = 300
TEAMS = {"logistics", "payments", "tech", "trust_safety", "catalog"}
AUTO_HANDLE = {
    "track_order",
    "delivery_period",
    "delivery_options",
    "check_payment_methods",
    "check_refund_policy",
    "recover_password",
    "praise",
    "packaging_feedback",
    "other",
}
MONEY_ACTIONS = {"issue_refund", "issue_credit"}


def _num(v: Any, default: float = 0.0) -> float:
    try:
        return float(str(v).replace(",", "").replace("SAR", "").strip())
    except (TypeError, ValueError):
        return default


def gate(decision: dict, *, intent: str, customers: int, max_order_sar: float = REFUND_CAP) -> dict:
    """Return a copy of `decision` whose actions obey `_shared/policies.md`."""
    d = copy.deepcopy(decision)
    notes: list[str] = list(d.get("policy_notes") or [])
    allowed = contracts.catalog_types()
    kept: list[dict] = []
    for a in d.get("actions") or []:
        if not isinstance(a, dict):
            continue
        t = a.get("type")
        params = a.get("params") if isinstance(a.get("params"), dict) else {}
        a = {"type": t, "params": params, "why": str(a.get("why") or "")[:200]}
        if t not in allowed:
            notes.append(f"Dropped '{t}': not in the action catalog.")
            continue
        if intent == "account_security" and t in MONEY_ACTIONS:
            notes.append("Security issue: money action replaced by escalation to trust & safety (policy 6).")
            kept.append({"type": "escalate_to_team", "params": {"team": "trust_safety", "note": "Possible account compromise"}, "why": "Policy 6"})
            continue
        if t == "issue_refund":
            amt = _num(params.get("amount_sar_each"), 0)
            cap = min(REFUND_CAP, max_order_sar or REFUND_CAP)
            if amt <= 0:
                amt = cap
                notes.append(f"Refund amount missing: set to SAR {cap:.0f} cap.")
            if amt > REFUND_CAP:
                notes.append(f"Refund SAR {amt:.0f} is above the SAR {REFUND_CAP} cap: changed to escalation to payments (policy 2).")
                kept.append({"type": "escalate_to_team", "params": {"team": "payments", "note": f"Refund request of SAR {amt:.0f} each needs payments approval"}, "why": "Above refund cap"})
                continue
            params["amount_sar_each"] = round(min(amt, cap))
        if t == "issue_credit":
            amt = _num(params.get("amount_sar_each"), 50)
            if amt > CREDIT_CAP:
                notes.append(f"Credit lowered from SAR {amt:.0f} to the SAR {CREDIT_CAP} cap (policy 3).")
                amt = CREDIT_CAP
            params["amount_sar_each"] = round(max(amt, 5))
        if t == "escalate_to_team" and params.get("team") not in TEAMS:
            params["team"] = "logistics" if "deliver" in intent else "payments" if intent in {"payment_issue", "get_refund", "track_refund", "price_or_promo_issue"} else "tech"
        a["params"] = params
        kept.append(a)
    if not any(a["type"] == "send_reply_batch" for a in kept):
        kept.insert(0, {"type": "send_reply_batch", "params": {}, "why": "Every card answers the customers."})
    if customers > MAX_BATCH:
        notes.append(f"{customers} customers is above the batch limit: this card acts on the first {MAX_BATCH} (policy 4).")
    # one action of each type, money actions last
    seen: set[str] = set()
    deduped = [a for a in kept if not (a["type"] in seen or seen.add(a["type"]))]
    deduped.sort(key=lambda a: (a["type"] in MONEY_ACTIONS, a["type"] != "send_reply_batch"))
    d["actions"] = deduped[:4]
    d["policy_notes"] = notes
    return d
