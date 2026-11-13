"""Stage 01 (offline): raw public datasets -> DOO-shaped sample committed under data/sample/.

Run from the workspace root:
    python _tools/build_dataset.py

Reads (gitignored, see README "Datasets"):
    data/raw/twcs.csv          Customer Support on Twitter (Kaggle / HF mirror)
    data/raw/shein_ar.parquet  Arabic Reviews of SHEIN (HF, Apache-2.0)
    data/raw/bitext.csv        Bitext customer-support dataset (HF, CDLA-Sharing-1.0)

Writes:
    data/sample/messages.jsonl  shift + baseline messages (DOO schema: inbox/contact/conversation/message)
    data/sample/contacts.json   contacts with simulated tier + orders (simulated system of record)
    data/eval/bitext_eval.jsonl stratified labelled sample for _tools/eval_intents.py
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "sample"
EVAL = ROOT / "data" / "eval"

BRAND = "AmazonHelp"
# The shift we replay: Cyber Monday 2017, 12:00-24:00 UTC (the real peak day for @AmazonHelp).
SHIFT_START = datetime(2017, 11, 27, 12, 0, tzinfo=timezone.utc)
SHIFT_END = datetime(2017, 11, 28, 0, 0, tzinfo=timezone.utc)
BASELINE_START = datetime(2017, 11, 13, tzinfo=timezone.utc)
BASELINE_END = datetime(2017, 11, 27, tzinfo=timezone.utc)
SHIFT_EN_MAX = 1100
BASELINE_EN = 1400
SEED = 7

URL_RE = re.compile(r"https?://\S+")
HANDLE_RE = re.compile(r"^(\s*@\w+\s*)+")


def clean_tweet(text: str) -> str:
    text = HANDLE_RE.sub("", text)
    text = URL_RE.sub("[link]", text)
    return re.sub(r"\s+", " ", text).strip()


def stable_int(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest()[:12], 16)


def load_twcs() -> pd.DataFrame:
    cache = RAW / "twcs.parquet"
    if cache.exists():
        df = pd.read_parquet(cache)
    else:
        df = pd.read_csv(RAW / "twcs.csv")
        df["ts"] = pd.to_datetime(df.created_at, format="%a %b %d %H:%M:%S %z %Y")
        df.to_parquet(cache)
    brand = df[df.author_id == BRAND]
    answered = set(brand.in_response_to_tweet_id.dropna().astype("int64"))
    # Opening customer tweets of a thread that the brand answered.
    openers = df[df.inbound & df.tweet_id.isin(answered) & df.in_response_to_tweet_id.isna()].copy()
    openers["clean"] = openers.text.map(clean_tweet)
    openers = openers[openers.clean.str.len() >= 25]
    # Keep mostly-ASCII (English) tweets; Arabic comes from its own dataset.
    openers = openers[openers.clean.map(lambda t: sum(c.isascii() for c in t) / len(t) > 0.9)]
    return openers


def contact_record(contact_id: str) -> dict:
    """Simulated system of record for one contact. Deterministic from the id."""
    rng = random.Random(stable_int(contact_id))
    tier = "vip" if rng.random() < 0.06 else ("loyal" if rng.random() < 0.25 else "standard")
    orders = []
    for _ in range(rng.randint(1, 3)):
        amount = round(min(2400, max(19, rng.lognormvariate(4.6, 0.8))), 0)
        orders.append(
            {
                "order_id": f"ORD-{rng.randint(100000, 999999)}",
                "amount_sar": amount,
                "status": rng.choice(["delivered", "in_transit", "in_transit", "processing", "delivered"]),
            }
        )
    return {"contact_id": contact_id, "tier": tier, "orders": orders}


def main() -> int:
    rng = random.Random(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    EVAL.mkdir(parents=True, exist_ok=True)

    tw = load_twcs()
    shift = tw[(tw.ts >= SHIFT_START) & (tw.ts < SHIFT_END)].sort_values("ts")
    if len(shift) > SHIFT_EN_MAX:  # thin evenly so the timeline keeps its real shape
        shift = shift.iloc[:: max(1, len(shift) // SHIFT_EN_MAX)].head(SHIFT_EN_MAX)
    base = tw[(tw.ts >= BASELINE_START) & (tw.ts < BASELINE_END)].sample(BASELINE_EN, random_state=SEED)

    ar = pd.read_parquet(RAW / "shein_ar.parquet")
    ar = ar[ar.label <= 2].copy()  # 1-2 star reviews = complaints
    ar["clean"] = ar.raw_text.str.replace(r"\s+", " ", regex=True).str.strip()
    ar = ar[ar.clean.str.len() >= 8].sample(frac=1.0, random_state=SEED)
    half = len(ar) // 2
    ar_shift, ar_base = ar.iloc[:half], ar.iloc[half:]

    messages: list[dict] = []
    contacts: dict[str, dict] = {}

    def add(window: str, ts: datetime, text: str, lang: str, channel: str, source: str, ref: str, author: str):
        cid = f"c_{stable_int(source + author) % 10_000_000:07d}"
        contacts.setdefault(cid, contact_record(cid))
        mid = f"m_{stable_int(source + ref) % 10**10:010d}"
        messages.append(
            {
                "id": mid,
                "conversation_id": f"conv_{mid[2:]}",
                "contact_id": cid,
                "inbox": channel,
                "channel": channel,
                "lang_hint": lang,
                "ts": ts.isoformat(),
                "window": window,
                "text": text,
                "source": source,
                "source_ref": ref,
            }
        )

    for _, r in shift.iterrows():
        add("shift", r.ts.to_pydatetime(), r.clean, "en", "twitter", "twcs", str(r.tweet_id), str(r.author_id))
    for _, r in base.iterrows():
        add("baseline", r.ts.to_pydatetime(), r.clean, "en", "twitter", "twcs", str(r.tweet_id), str(r.author_id))
    span = (SHIFT_END - SHIFT_START).total_seconds()
    for i, r in ar_shift.iterrows():  # reviews carry no timestamp: re-timed into the shift (documented)
        ts = SHIFT_START + timedelta(seconds=rng.random() * span)
        add("shift", ts, r.clean, "ar", "app_review", "shein_ar", str(i), f"ar{i}")
    bspan = (BASELINE_END - BASELINE_START).total_seconds()
    for i, r in ar_base.iterrows():
        ts = BASELINE_START + timedelta(seconds=rng.random() * bspan)
        add("baseline", ts, r.clean, "ar", "app_review", "shein_ar", str(i), f"ar{i}")

    messages.sort(key=lambda m: m["ts"])
    with (OUT / "messages.jsonl").open("w", encoding="utf-8") as f:
        for m in messages:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    (OUT / "contacts.json").write_text(json.dumps(contacts, ensure_ascii=False, indent=0), encoding="utf-8")

    bt = pd.read_csv(RAW / "bitext.csv")
    ev = bt.groupby("intent").sample(20, random_state=SEED)
    with (EVAL / "bitext_eval.jsonl").open("w", encoding="utf-8") as f:
        for _, r in ev.iterrows():
            f.write(json.dumps({"text": r.instruction, "intent": r.intent, "category": r.category}) + "\n")

    n_shift = sum(m["window"] == "shift" for m in messages)
    print(f"messages: {len(messages)} (shift {n_shift}, baseline {len(messages) - n_shift})")
    print(f"arabic: {len(ar)}  contacts: {len(contacts)}  bitext eval: {len(ev)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
