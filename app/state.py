"""Live state: the shared base (pipeline outputs) and one sandbox per visitor.

Every visitor gets their own Session, so a judge's first 30 seconds always start from the same
shift, and nothing one visitor approves changes another's screen.
"""
from __future__ import annotations

import json
import random
import threading
import time
import uuid
from collections import Counter, OrderedDict
from dataclasses import dataclass, field

import numpy as np

from . import act
from .config import settings
from .llm import LLMError
from .pipeline import decide, infer, patterns
from .pipeline.vectors import Vectorizer
from .policy import AUTO_HANDLE

STATE = settings.data_dir / "state"
SAMPLE = settings.data_dir / "sample"
TAIL = 45          # shift messages replayed live, one every REPLAY_SECONDS
FIRST_ARRIVAL = 7  # seconds after opening until the first live message lands
MAX_OPEN = 5       # cards on screen at once


class Base:
    """Read-only pipeline outputs, loaded once."""

    def __init__(self) -> None:
        self.msgs = {m["id"]: m for m in (json.loads(x) for x in (SAMPLE / "messages.jsonl").open(encoding="utf-8"))}
        self.contacts = json.loads((SAMPLE / "contacts.json").read_text(encoding="utf-8"))
        self.infs = {r["id"]: r for r in (json.loads(x) for x in (STATE / "inferences.jsonl").open(encoding="utf-8"))}
        clusters = json.loads((STATE / "clusters.json").read_text(encoding="utf-8"))
        self.clusters = {c["id"]: c for c in clusters}
        self.vectorizer = Vectorizer.load(STATE / "vectorizer.json")
        ids = list(self.infs)
        mat = self.vectorizer.transform(patterns.embed_text(self.infs[i]) for i in ids)
        self.vec_of = {i: mat[k] for k, i in enumerate(ids)}
        # Member matrices per cluster: live messages route to the cluster of their nearest neighbour.
        self.member_mat = {c["id"]: np.stack([self.vec_of[m] for m in c["message_ids"]]) for c in clusters}
        self.decisions = {d["card_id"]: d for d in json.loads((STATE / "decisions.json").read_text(encoding="utf-8"))}
        self.cluster_of = {mid: c["id"] for c in clusters for mid in c["message_ids"]}
        shift = sorted((m for m in self.msgs.values() if m["window"] == "shift" and m["id"] in self.infs), key=lambda m: m["ts"])
        # Replay tail: messages that belong to a card cluster arrive live, so the screen visibly moves.
        card_msgs = [m["id"] for m in shift if self.cluster_of.get(m["id"]) in self.decisions]
        rnd = random.Random(11)
        tail = set(rnd.sample(card_msgs[len(card_msgs) // 2 :], min(TAIL, len(card_msgs) // 2)))
        self.tail = [m["id"] for m in shift if m["id"] in tail]
        self.pre = [m["id"] for m in shift if m["id"] not in tail]
        self.eval_report = self._eval_report()

    def _eval_report(self) -> dict:
        p = settings.data_dir / "eval" / "report.md"
        if not p.exists():
            return {}
        text = p.read_text(encoding="utf-8")
        acc = next((ln for ln in text.splitlines() if ln.startswith("- Accuracy")), "")
        n = next((ln for ln in text.splitlines() if ln.startswith("- Examples")), "")
        return {"verdict": text.splitlines()[0], "accuracy": acc.split("**")[1] if "**" in acc else "", "examples": n.replace("- Examples: ", "")}

    def max_order(self, member_ids: list[str]) -> float:
        amounts = [self.contacts[self.msgs[i]["contact_id"]]["orders"][0]["amount_sar"] for i in member_ids if self.contacts.get(self.msgs[i]["contact_id"], {}).get("orders")]
        return float(np.median(amounts)) if amounts else 500.0


@dataclass
class Session:
    id: str
    started: float = field(default_factory=time.time)
    status: dict = field(default_factory=dict)  # card -> open|done|snoozed
    decisions: dict = field(default_factory=dict)  # card -> decision overriding the base one
    executed: dict = field(default_factory=dict)  # card -> execution record
    intent_override: dict = field(default_factory=dict)  # message -> intent (from corrections)
    corrections: list = field(default_factory=list)
    learned: dict = field(default_factory=dict)  # card -> note shown on the card
    injected: dict = field(default_factory=dict)  # message id -> message
    inj_infs: dict = field(default_factory=dict)
    inj_cluster: dict = field(default_factory=dict)  # message id -> cluster id
    live_clusters: dict = field(default_factory=dict)  # cluster id -> cluster (session-only)
    live_cards: list = field(default_factory=list)  # card ids created live by the agent
    traces: list = field(default_factory=list)
    toasts: list = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    version: int = 0

    def bump(self, toast: str | None = None) -> None:
        self.version += 1
        if toast:
            self.toasts.append({"v": self.version, "text": toast})
            self.toasts = self.toasts[-5:]


class Engine:
    def __init__(self, base: Base) -> None:
        self.base = base
        self.sessions: OrderedDict[str, Session] = OrderedDict()
        self._lock = threading.Lock()

    # ---- sessions -------------------------------------------------------------------------
    def session(self, sid: str | None) -> Session:
        with self._lock:
            if sid and sid in self.sessions:
                self.sessions.move_to_end(sid)
                return self.sessions[sid]
            s = Session(id=uuid.uuid4().hex[:16])
            self.sessions[s.id] = s
            while len(self.sessions) > settings.max_sessions:
                self.sessions.popitem(last=False)
            return s

    def arrived(self, s: Session) -> int:
        elapsed = time.time() - s.started - FIRST_ARRIVAL
        return 0 if elapsed < 0 else min(len(self.base.tail), int(elapsed // settings.replay_seconds) + 1)

    def visible_ids(self, s: Session) -> list[str]:
        return self.base.pre + self.base.tail[: self.arrived(s)]

    def now_label(self, s: Session) -> str:
        ids = self.visible_ids(s)
        last = max(self.base.msgs[i]["ts"] for i in ids)
        return last[11:16]

    # ---- views ----------------------------------------------------------------------------
    def inf(self, s: Session, mid: str) -> dict:
        r = s.inj_infs.get(mid) or self.base.infs[mid]
        if mid in s.intent_override:
            r = dict(r, intent=s.intent_override[mid])
        return r

    def msg(self, s: Session, mid: str) -> dict:
        return s.injected.get(mid) or self.base.msgs[mid]

    def members(self, s: Session, cid: str, visible: set[str]) -> list[str]:
        if cid in s.live_clusters:
            return list(s.live_clusters[cid]["message_ids"])
        base = [m for m in self.base.clusters[cid]["message_ids"] if m in visible]
        return base + [m for m, c in s.inj_cluster.items() if c == cid]

    def decision(self, s: Session, cid: str) -> dict:
        return s.decisions.get(cid) or self.base.decisions[cid]

    def cards(self, s: Session) -> dict:
        visible = set(self.visible_ids(s))
        all_msgs = {**self.base.msgs, **s.injected}
        all_infs = {i: self.inf(s, i) for i in list(visible) + list(s.injected)}
        cards = []
        for cid in list(self.base.decisions) + s.live_cards:
            cl = s.live_clusters.get(cid) or self.base.clusters[cid]
            mids = self.members(s, cid, visible)
            if not mids:
                continue
            st = patterns.stats(mids, cl["intent"], all_msgs, all_infs, self.base.contacts)
            d = self.decision(s, cid)
            arrived_live = [m for m in mids if m in self.base.tail or m in s.injected]
            cards.append(
                {
                    "id": cid,
                    "intent": all_infs[mids[0]]["intent"],
                    "group": cl["intent"],
                    "stats": st,
                    "lift": cl["lift"],
                    "new": cl.get("new", False),
                    "score": patterns.score(st, cl["lift"]),
                    "decision": d,
                    "status": s.status.get(cid, "open"),
                    "execution": s.executed.get(cid),
                    "learned": s.learned.get(cid),
                    "agent_initiated": cid in s.live_cards or cl["lift"] >= 2 or cl.get("new"),
                    "live_count": len(arrived_live),
                    "evidence": [self.msg(s, e) | {"inf": all_infs.get(e) or self.inf(s, e)} for e in d.get("evidence_ids", []) if e in all_msgs][:6],
                    "first_ts": cl.get("first_ts", "")[11:16],
                }
            )
        cards.sort(key=lambda c: c["score"], reverse=True)
        open_cards = [c for c in cards if c["status"] == "open"][:MAX_OPEN]
        done = [c for c in cards if c["status"] == "done"]
        # Everything not on a card was resolved by the AI agent's normal flow (simulated, like DOO's
        # agents): the supervisor only sees it as one line.
        on_cards = {m for cid in list(self.base.decisions) + s.live_cards for m in self.members(s, cid, visible)}
        handled = Counter(self.inf(s, i)["intent"] for i in visible if i not in on_cards)
        all_open = [c for c in cards if c["status"] == "open"]
        return {
            "open": open_cards,
            "done": done,
            "remaining": len(open_cards),
            "queued": max(0, len(all_open) - len(open_cards)),
            "on_cards": len(on_cards),
            "handled_total": sum(handled.values()),
            "handled": handled.most_common(6),
            "messages": len(visible) + len(s.injected),
            "now": self.now_label(s),
            "totals": self.totals(s),
        }

    def totals(self, s: Session) -> dict:
        t = Counter()
        for rec in s.executed.values():
            e = rec["effects"]
            t["replies"] += sum(e["replies"].values())
            t["refund_sar"] += e["refund_sar"]
            t["credit_sar"] += e["credit_sar"]
            t["tickets"] += len(e["tickets"])
            t["knowledge"] += 1 if e["knowledge"] else 0
            t["decisions"] += 1
        return dict(t)

    def card(self, s: Session, cid: str) -> dict | None:
        view = self.cards(s)
        return next((c for c in view["open"] + view["done"] if c["id"] == cid), None) or self._any_card(s, cid)

    def _any_card(self, s: Session, cid: str) -> dict | None:
        saved = s.status.get(cid)
        s.status[cid] = "open"
        try:
            view = self.cards(s)
            return next((c for c in view["open"] if c["id"] == cid), None)
        finally:
            if saved is None:
                s.status.pop(cid, None)
            else:
                s.status[cid] = saved

    # ---- stage 06: decisions -------------------------------------------------------------
    def approve(self, s: Session, cid: str, edits: dict) -> dict:
        from .policy import gate

        with s.lock:
            d = json.loads(json.dumps(self.decision(s, cid)))
            changed = []
            for k in ("reply_en", "reply_ar"):
                if edits.get(k) is not None and edits[k].strip() != d.get(k, "").strip():
                    d[k] = edits[k].strip()
                    changed.append(k)
            for n, a in enumerate(d["actions"]):  # amounts first: indexes refer to the drafted list
                v = edits.get(f"amount_{n}")
                if v not in (None, "") and "amount_sar_each" in a["params"]:
                    try:
                        new = float(v)
                    except ValueError:
                        continue
                    if new != float(a["params"]["amount_sar_each"]):
                        a["params"]["amount_sar_each"] = new
                        changed.append(f"amount_{n}")
            keep = edits.get("keep")
            if keep is not None:
                before = len(d["actions"])
                d["actions"] = [a for n, a in enumerate(d["actions"]) if str(n) in keep]
                if len(d["actions"]) != before:
                    changed.append("actions")
            cl = s.live_clusters.get(cid) or self.base.clusters[cid]
            visible = set(self.visible_ids(s))
            mids = self.members(s, cid, visible)
            d = gate(d, intent=cl["intent"], customers=len(mids), max_order_sar=self.base.max_order([m for m in mids if m in self.base.msgs]))
            all_msgs = {**self.base.msgs, **s.injected}
            all_infs = {m: self.inf(s, m) for m in mids}
            rec = act.execute(d, mids, all_msgs, all_infs, self.base.contacts)
            rec["edited"] = changed
            rec["digest"] = act.audit(s.id, cid, "approve", {"actions": d["actions"], "reply_en": d["reply_en"], "reply_ar": d["reply_ar"], "customers": rec["customers"]})
            s.decisions[cid] = d
            s.executed[cid] = rec
            s.status[cid] = "done"
            s.bump()
            return rec

    def undo(self, s: Session, cid: str) -> bool:
        with s.lock:
            rec = s.executed.get(cid)
            if not rec:
                return False
            late = time.time() > rec["undo_until"]
            act.audit(s.id, cid, "compensate" if late else "undo", {"reversed": rec["effects"], "digest": rec.get("digest")})
            s.executed.pop(cid)
            s.status[cid] = "open"
            s.bump("Reversed. Nothing more goes out for this card." if not late else "Compensating actions recorded in the log.")
            return True

    def snooze(self, s: Session, cid: str) -> None:
        with s.lock:
            s.status[cid] = "snoozed"
            act.audit(s.id, cid, "snooze", {})
            s.bump("Snoozed. It comes back if it grows.")

    def reject(self, s: Session, cid: str, alt_index: int | None, custom: str, reason: str) -> dict:
        """'Not this': adopt an alternative hypothesis (or the person's own), re-draft, learn."""
        with s.lock:
            d = self.decision(s, cid)
            cl = s.live_clusters.get(cid) or self.base.clusters[cid]
            visible = set(self.visible_ids(s))
            mids = self.members(s, cid, visible)
            if alt_index is not None and 0 <= alt_index < len(d.get("alternatives", [])):
                alt = d["alternatives"][alt_index]
                new_intent, new_hyp = alt["intent"], alt["hypothesis"]
            else:
                new_intent, new_hyp = cl["intent"], custom.strip()[:120] or "something else"
            from_intent = cl["intent"]
            evidence = [{"id": e, "language": self.inf(s, e)["language"], "text": self.msg(s, e)["text"]} for e in d.get("evidence_ids", []) if e in self.base.msgs or e in s.injected]
            override = {"rejected_hypothesis": d["hypothesis"], "correct_hypothesis": new_hyp}
            try:
                nd = decide.draft(dict(cl, intent=new_intent), evidence, self.base.max_order([m for m in mids if m in self.base.msgs]), override=override)
            except LLMError:
                nd = dict(d, title=new_hyp[:1].upper() + new_hyp[1:], hypothesis=new_hyp, alternatives=[], policy_notes=d.get("policy_notes", []) + ["Re-draft unavailable (model offline): actions kept from the first draft. Edit before approving."])
            nd.update({"card_id": cid, "cluster_id": cid, "evidence_ids": d.get("evidence_ids", [])})
            nd["confidence"] = max(nd.get("confidence", 0.8), 0.8)  # the person just confirmed the hypothesis
            nd["question"] = None
            s.decisions[cid] = nd
            moved = 0
            if new_intent != from_intent:
                for m in mids:
                    s.intent_override[m] = new_intent
                    moved += 1
            for e in evidence[:4]:
                c = {"text": e["text"], "from_intent": from_intent, "to_intent": new_intent if new_intent != from_intent else f"{from_intent} ({new_hyp})", "card": cid}
                s.corrections.append(c)
                act.record_correction(s.id, cid, e["id"], from_intent, c["to_intent"], reason)
            act.audit(s.id, cid, "reject", {"was": d["hypothesis"], "now": new_hyp, "reason": reason, "moved": moved})
            s.learned[cid] = {"was": d["hypothesis"], "now": new_hyp, "moved": moved}
            s.status[cid] = "open"
            s.bump(f"Learned: “{d['hypothesis']}” → “{new_hyp}”. Applied to {len(mids)} messages and to new ones like them.")
            return nd

    def answer(self, s: Session, cid: str, option: str) -> dict:
        with s.lock:
            d = self.decision(s, cid)
            cl = s.live_clusters.get(cid) or self.base.clusters[cid]
            evidence = [{"id": e, "language": self.inf(s, e)["language"], "text": self.msg(s, e)["text"]} for e in d.get("evidence_ids", []) if e in self.base.msgs or e in s.injected]
            mids = self.members(s, cid, set(self.visible_ids(s)))
            try:
                nd = decide.draft(cl, evidence, self.base.max_order([m for m in mids if m in self.base.msgs]), override={"supervisor_answer": f"{(d.get('question') or {}).get('prompt', '')} -> {option}"})
            except LLMError:
                nd = dict(d)
            nd.update({"card_id": cid, "cluster_id": cid, "evidence_ids": d.get("evidence_ids", []), "question": None})
            nd["confidence"] = max(nd.get("confidence", 0.8), 0.8)
            s.decisions[cid] = nd
            act.audit(s.id, cid, "answer", {"question": (d.get("question") or {}).get("prompt"), "answer": option})
            s.bump("Got it. Drafted from your answer.")
            return nd

    # ---- live inbound ----------------------------------------------------------------------
    def inbound(self, s: Session, text: str, channel: str = "whatsapp") -> dict:
        """A new customer message (the DOO webhook): classify (real model call), vectorise, route."""
        t0 = time.time()
        mid = f"live_{uuid.uuid4().hex[:10]}"
        contact = f"c_live_{uuid.uuid4().hex[:6]}"
        self.base.contacts.setdefault(contact, {"contact_id": contact, "tier": "standard", "orders": [{"order_id": "ORD-LIVE", "amount_sar": 180, "status": "in_transit"}]})
        msg = {"id": mid, "conversation_id": f"conv_{mid}", "contact_id": contact, "inbox": channel, "channel": channel, "lang_hint": None, "ts": "", "window": "shift", "text": text[:600], "source": "live", "source_ref": ""}
        inf = infer.classify_batch([msg], s.corrections, use_cache=False)[0]
        t_inf = time.time()
        route, joined = "none", None
        vec = self.base.vectorizer.transform([patterns.embed_text(inf)])[0]
        best, best_sim = None, 0.0
        for c in list(self.base.clusters.values()) + list(s.live_clusters.values()):
            if c["intent"] != inf["intent"] or c["id"].endswith("-other"):
                continue
            mat = self.base.member_mat.get(c["id"]) if c["id"] in self.base.member_mat else c.get("_mat")
            if mat is None or not len(mat):
                continue
            sim = float((mat @ vec).max())
            if sim > best_sim:
                best, best_sim = c, sim
        with s.lock:
            s.injected[mid] = msg | {"ts": self.base.msgs[self.visible_ids(s)[-1]]["ts"]}
            s.inj_infs[mid] = inf
            if inf["injection"]:
                route = "flagged"  # never grouped, never drafted from
            elif best is not None and best_sim >= patterns.SIM:
                s.inj_cluster[mid] = best["id"]
                joined = best["id"]
                route = "card" if (best["id"] in self.base.decisions or best["id"] in s.live_cards) else ("auto" if best.get("auto_handled") else "cluster")
                if best["id"] in s.live_clusters:
                    best["message_ids"].append(mid)
                    best["_mat"] = np.vstack([best["_mat"], vec[None, :]])
            elif inf["intent"] in AUTO_HANDLE:
                route = "auto"
            else:
                cid = f"live-{inf['intent']}-{len(s.live_clusters)}"
                s.live_clusters[cid] = {"id": cid, "intent": inf["intent"], "message_ids": [mid], "issues": [inf["issue"]], "lift": 5.0, "new": True, "auto_handled": inf["intent"] in AUTO_HANDLE, "first_ts": "", "_mat": vec[None, :], "size": 1}
                s.inj_cluster[mid] = cid
                joined, route = cid, "new"
            trace = {"id": mid, "text": text[:600], "inf": inf, "route": route, "cluster": joined, "similarity": round(best_sim, 3), "ms_infer": int((t_inf - t0) * 1000), "ms_total": int((time.time() - t0) * 1000), "used_corrections": len(s.corrections)}
            s.traces.insert(0, trace)
            s.traces = s.traces[:8]
        # Live traffic that forms a pattern (2+ new messages on a group with no card yet) makes the
        # agent draft a card on its own: a brand-new issue, or a quiet issue that is now growing.
        if joined and joined not in s.live_cards and joined not in self.base.decisions and route in ("new", "cluster"):
            fresh = sum(1 for c in s.inj_cluster.values() if c == joined)
            if fresh >= 2 and self._live_card(s, joined):
                trace["route"] = "new_card"
        with s.lock:
            s.bump({"card": "Joined a decision card.", "new_card": "New pattern: the agent drafted a decision for it.", "new": "New issue. One more like it and the agent drafts a decision.", "auto": "Answered by the agent alone.", "cluster": "Grouped with similar messages.", "flagged": "Instruction attempt flagged for a person."}.get(trace["route"]))
        return trace

    def _live_card(self, s: Session, cid: str) -> bool:
        all_msgs = {**self.base.msgs, **s.injected}
        if cid in s.live_clusters:
            lc = s.live_clusters[cid]
            mids = list(lc["message_ids"])
        else:  # a quiet base cluster that live traffic just made grow
            lc = dict(self.base.clusters[cid])
            mids = self.members(s, cid, set(self.visible_ids(s)))
        infs = {m: self.inf(s, m) for m in mids}
        lc.update(patterns.stats(mids, lc["intent"], all_msgs, infs, self.base.contacts))
        fresh = [m for m in mids if m in s.injected]
        older = [m for m in mids if m not in s.injected]
        evidence_ids = (fresh + older)[:6]
        lc["issues"] = list(dict.fromkeys(infs[m]["issue"] for m in evidence_ids))
        evidence = [{"id": m, "language": infs[m]["language"], "text": all_msgs[m]["text"]} for m in evidence_ids]
        try:
            d = decide.draft(lc, evidence, self.base.max_order([m for m in mids if m in self.base.msgs]) if older else 500.0, use_cache=False)
        except LLMError:
            return False
        d.update({"card_id": cid, "cluster_id": cid, "evidence_ids": evidence_ids})
        with s.lock:
            s.decisions[cid] = d
            s.live_cards.append(cid)
        return True
