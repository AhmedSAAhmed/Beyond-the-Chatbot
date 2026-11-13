"""Stage 03: cluster same-problem messages and measure what is spiking (see references/clustering.md)."""
from __future__ import annotations

import math
from collections import Counter
from typing import Iterable

import numpy as np

from ..policy import AUTO_HANDLE

SIM = 0.42
MONEY_INTENTS = {
    "get_refund",
    "track_refund",
    "payment_issue",
    "price_or_promo_issue",
    "damaged_or_defective",
    "wrong_or_misdescribed_item",
    "delivery_problem",
    "cancel_order",
}


def normalize(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=-1, keepdims=True)
    return m / np.where(n == 0, 1, n)


def embed_text(inf: dict, msg: dict | None = None) -> str:
    """What gets vectorised: the model's normalised English issue phrase (works for every language)."""
    return inf["issue"]


def centroid(member_ids: list[str], vec_of: dict) -> np.ndarray:
    return normalize(np.stack([vec_of[i] for i in member_ids if i in vec_of]).mean(axis=0))


def greedy_cluster(ids: list[str], vecs: np.ndarray, sim: float = SIM) -> list[list[int]]:
    """Return clusters as lists of row indices. Single pass, running-mean centroids."""
    cents: list[np.ndarray] = []
    members: list[list[int]] = []
    for i in range(len(ids)):
        v = vecs[i]
        if cents:
            sims = np.array([float(c @ v) for c in cents])
            j = int(sims.argmax())
            if sims[j] >= sim:
                members[j].append(i)
                k = len(members[j])
                c = cents[j] * ((k - 1) / k) + v / k
                cents[j] = c / (np.linalg.norm(c) or 1)
                continue
        cents.append(v.copy())
        members.append([i])
    return members


def stats(member_ids: Iterable[str], intent: str, msgs: dict, infs: dict, contacts: dict) -> dict:
    ids = list(member_ids)
    custs = {msgs[i]["contact_id"] for i in ids}
    vip = sum(contacts.get(c, {}).get("tier") == "vip" for c in custs)
    sar = 0.0
    if intent in MONEY_INTENTS:
        for c in custs:
            orders = contacts.get(c, {}).get("orders") or []
            if orders:
                sar += float(orders[0]["amount_sar"])
    sents = [infs[i]["sentiment"] for i in ids]
    high = sum(infs[i]["urgency"] == "high" for i in ids)
    langs = Counter(infs[i]["language"] for i in ids)
    return {
        "size": len(ids),
        "customers": len(custs),
        "vip": vip,
        "sar_at_risk": round(sar),
        "sentiment": round(sum(sents) / len(sents), 2) if sents else 0.0,
        "high_urgency_share": round(high / len(ids), 3) if ids else 0.0,
        "langs": dict(langs.most_common()),
        "injections": sum(bool(infs[i].get("injection")) for i in ids),
    }


def score(s: dict, lift: float) -> float:
    impact = s["customers"] * (1 + 2 * (s["vip"] / max(s["customers"], 1))) * (1 + s["sar_at_risk"] / 5000)
    urgency = max(0.0, -s["sentiment"]) / 2 + s["high_urgency_share"]
    return round(impact**0.8 * (1 + urgency) * (1 + 0.5 * math.log2(max(lift, 1.0))), 3)


def build_clusters(msgs: dict, infs: dict, vec_of: dict[str, np.ndarray], contacts: dict) -> tuple[list[dict], dict[str, np.ndarray]]:
    shift = [m for m in msgs.values() if m["window"] == "shift" and m["id"] in infs]
    base = [m for m in msgs.values() if m["window"] == "baseline" and m["id"] in vec_of and m["id"] in infs]
    shift.sort(key=lambda m: m["ts"])
    by_intent: dict[str, list[dict]] = {}
    for m in shift:
        by_intent.setdefault(infs[m["id"]]["intent"], []).append(m)

    clusters: list[dict] = []
    centroids: dict[str, np.ndarray] = {}
    for intent, ms in by_intent.items():
        ids = [m["id"] for m in ms if m["id"] in vec_of]
        if not ids:
            continue
        vecs = normalize(np.stack([vec_of[i] for i in ids]))
        groups = greedy_cluster(ids, vecs)
        big = sorted((g for g in groups if len(g) >= 3), key=len, reverse=True)
        small = [i for g in groups if len(g) < 3 for i in g]
        named = [(f"{intent}-{n}", g) for n, g in enumerate(big)]
        if small:
            named.append((f"{intent}-other", small))  # one-offs: counted, never a card of their own
        for cid, g in named:
            mids = [ids[i] for i in g]
            centroids[cid] = normalize(vecs[g].mean(axis=0))
            issues = Counter(infs[i]["issue"].lower() for i in mids)
            clusters.append({"id": cid, "intent": intent, "message_ids": mids, "issues": [k for k, _ in issues.most_common(5)]})

    # Baseline: a past message counts for the cluster holding its nearest shift neighbour (same
    # intent, cosine >= SIM). Nearest-neighbour, not centroid, so broad clusters are not starved.
    owner = {mid: c["id"] for c in clusters for mid in c["message_ids"]}
    base_counts: Counter = Counter()
    for intent, ms in by_intent.items():
        ids = [m["id"] for m in ms if m["id"] in vec_of]
        bids = [m["id"] for m in base if infs[m["id"]]["intent"] == intent]
        if not ids or not bids:
            continue
        sims = np.stack([vec_of[b] for b in bids]) @ np.stack([vec_of[i] for i in ids]).T
        for row in sims:
            j = int(row.argmax())
            if row[j] >= SIM:
                base_counts[owner[ids[j]]] += 1
    n_shift, n_base = max(len(shift), 1), max(len(base), 1)
    for c in clusters:
        s = stats(c["message_ids"], c["intent"], msgs, infs, contacts)
        share_s = s["size"] / n_shift
        share_b = max(base_counts[c["id"]] / n_base, 0.5 / n_base)
        lift = round(share_s / share_b, 2)
        c.update(s)
        c["baseline"] = base_counts[c["id"]]
        c["lift"] = lift
        c["new"] = base_counts[c["id"]] == 0 and s["size"] >= 3
        c["score"] = score(s, lift)
        c["auto_handled"] = c["intent"] in AUTO_HANDLE and lift < 3
        ts = sorted(msgs[i]["ts"] for i in c["message_ids"])
        c["first_ts"], c["last_ts"] = ts[0], ts[-1]
    clusters.sort(key=lambda c: c["score"], reverse=True)
    return clusters, centroids


def representatives(cluster: dict, centroid: np.ndarray, vec_of: dict, infs: dict, k: int = 6) -> list[str]:
    """Closest messages to the centroid, keeping up to 2 non-English voices and no injections."""
    ids = [i for i in cluster["message_ids"] if i in vec_of and not infs[i].get("injection")]
    ids.sort(key=lambda i: -float(normalize(vec_of[i]) @ centroid))
    non_en = [i for i in ids if infs[i]["language"] != "en"][:2]
    en = [i for i in ids if infs[i]["language"] == "en"][: k - len(non_en)]
    return (en + non_en)[:k] or ids[:k]
