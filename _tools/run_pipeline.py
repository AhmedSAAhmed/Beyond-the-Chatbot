"""Run stages 02-04 offline over data/sample/ and write data/state/.

    python _tools/run_pipeline.py                 # all stages, resumes where it stopped
    python _tools/run_pipeline.py --stage 03      # one stage

Stage outputs (each is the next stage's input):
    02 -> data/state/inferences.jsonl
    03 -> data/state/vectorizer.json, clusters.json
    04 -> data/state/decisions.json  (+ warms the cache for every "Not this" redraft)
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.llm import usage  # noqa: E402
from app.pipeline import decide, infer, patterns  # noqa: E402
from app.pipeline.vectors import Vectorizer  # noqa: E402

SAMPLE = ROOT / "data" / "sample"
STATE = ROOT / "data" / "state"
BATCH = 15
MAX_CARDS = 8


def load_messages() -> dict[str, dict]:
    return {m["id"]: m for m in (json.loads(x) for x in (SAMPLE / "messages.jsonl").open(encoding="utf-8"))}


def load_infs() -> dict[str, dict]:
    p = STATE / "inferences.jsonl"
    if not p.exists():
        return {}
    return {r["id"]: r for r in (json.loads(x) for x in p.open(encoding="utf-8"))}


def stage02(msgs: dict, workers: int) -> None:
    done = load_infs()
    todo = [m for m in msgs.values() if m["id"] not in done]
    print(f"[02] {len(done)} done, {len(todo)} to classify")
    batches = [todo[i : i + BATCH] for i in range(0, len(todo), BATCH)]
    with (STATE / "inferences.jsonl").open("a", encoding="utf-8") as f, ThreadPoolExecutor(workers) as ex:
        for n, out in enumerate(ex.map(_safe_classify, batches), 1):
            for r in out:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            if n % 10 == 0:
                print(f"[02] {n}/{len(batches)} batches")


def _safe_classify(batch: list[dict]) -> list[dict]:
    try:
        return infer.classify_batch(batch)
    except Exception as exc:  # one bad batch must not lose the run; it is retried next run
        print(f"[02] batch failed, will retry next run: {exc}")
        return []


def vectors(msgs: dict, infs: dict) -> tuple[Vectorizer, dict[str, np.ndarray]]:
    ids = [i for i in msgs if i in infs]
    vec = Vectorizer.fit(patterns.embed_text(infs[i]) for i in ids)
    mat = vec.transform(patterns.embed_text(infs[i]) for i in ids)
    return vec, {i: mat[k] for k, i in enumerate(ids)}


def stage03(msgs: dict, contacts: dict) -> None:
    infs = load_infs()
    vec, vec_of = vectors(msgs, infs)
    vec.save(STATE / "vectorizer.json")
    clusters, _ = patterns.build_clusters(msgs, infs, vec_of, contacts)
    (STATE / "clusters.json").write_text(json.dumps(clusters, ensure_ascii=False, indent=1), encoding="utf-8")
    cards = [c for c in clusters if not c["auto_handled"]]
    print(f"[03] {len(clusters)} clusters, {len(cards)} card candidates; top:")
    for c in cards[:12]:
        print(f"     {c['score']:8.1f}  {c['id']:32s} n={c['size']:3d} lift={c['lift']:5.2f} vip={c['vip']} {c['issues'][:2]}")


def _evidence(cluster: dict, cent: np.ndarray, vec_of: dict, infs: dict, msgs: dict) -> list[dict]:
    rep = patterns.representatives(cluster, cent, vec_of, infs)
    return [{"id": i, "language": infs[i]["language"], "text": msgs[i]["text"]} for i in rep]


def max_order(cluster: dict, msgs: dict, contacts: dict) -> float:
    amounts = [contacts[msgs[i]["contact_id"]]["orders"][0]["amount_sar"] for i in cluster["message_ids"] if contacts.get(msgs[i]["contact_id"], {}).get("orders")]
    return float(np.median(amounts)) if amounts else 500.0


def stage04(msgs: dict, contacts: dict, workers: int) -> None:
    infs = load_infs()
    clusters = json.loads((STATE / "clusters.json").read_text(encoding="utf-8"))
    _, vec_of = vectors(msgs, infs)
    cents = {c["id"]: patterns.centroid(c["message_ids"], vec_of) for c in clusters}
    picked = [c for c in clusters if not c["auto_handled"] and not c["id"].endswith("-other")][:MAX_CARDS]

    def one(c: dict) -> dict:
        ev = _evidence(c, cents[c["id"]], vec_of, infs, msgs)
        d = decide.draft(c, ev, max_order(c, msgs, contacts))
        d.update({"card_id": c["id"], "cluster_id": c["id"], "evidence_ids": [e["id"] for e in ev]})
        return d

    with ThreadPoolExecutor(workers) as ex:
        decisions = list(ex.map(one, picked))
    (STATE / "decisions.json").write_text(json.dumps(decisions, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[04] {len(decisions)} decisions")
    for d in decisions:
        print(f"     {d['card_id']:32s} conf={d['confidence']} {d['title']}")

    # Warm the cache for every "Not this" redraft so the live recovery path answers instantly.
    def warm(pair: tuple[dict, dict]) -> None:
        d, alt = pair
        c = next(x for x in clusters if x["id"] == d["cluster_id"])
        ev = _evidence(c, cents[c["id"]], vec_of, infs, msgs)
        cc = dict(c, intent=alt["intent"])
        decide.draft(cc, ev, max_order(c, msgs, contacts), override={"rejected_hypothesis": d["hypothesis"], "correct_hypothesis": alt["hypothesis"]})

    pairs = [(d, a) for d in decisions for a in d["alternatives"]]
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(warm, pairs))
    print(f"[04] warmed {len(pairs)} recovery redrafts")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["02", "03", "04"])
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    STATE.mkdir(parents=True, exist_ok=True)
    msgs = load_messages()
    contacts = json.loads((SAMPLE / "contacts.json").read_text(encoding="utf-8"))
    if args.stage in (None, "02"):
        stage02(msgs, args.workers)
    if args.stage in (None, "03"):
        stage03(msgs, contacts)
    if args.stage in (None, "04"):
        stage04(msgs, contacts, args.workers)
    print("model calls by provider:", dict(usage))
    return 0


if __name__ == "__main__":
    sys.exit(main())
