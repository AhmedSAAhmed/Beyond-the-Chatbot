"""Stage 03 vectors: local TF-IDF over the model's normalised issue phrase.

The language model already did the semantic work in stage 02: it wrote every complaint, in any
language, as a short English issue phrase ("package marked delivered but missing"). Grouping
those phrases needs no second model: hashed word + character-trigram TF-IDF, numpy only. No
quota, no network, identical offline and live.
"""
from __future__ import annotations

import json
import math
import re
import zlib
from collections import Counter
from pathlib import Path
from typing import Iterable

import numpy as np

DIM = 1024
STOP = {
    "a", "an", "the", "of", "to", "for", "and", "or", "in", "on", "at", "by", "with", "is", "are", "was",
    "be", "been", "it", "its", "my", "me", "i", "you", "your", "this", "that", "not", "no", "but", "after",
    "from", "as", "too", "very", "via", "about", "over", "than", "into", "out", "up", "still",
}
SYN = {"damage": "broken", "damaged": "broken", "defective": "broken", "faulty": "broken", "late": "delay", "delayed": "delay",
       "delays": "delay", "missing": "notreceived", "lost": "notreceived", "parcel": "package", "order": "package",
       "shipment": "package", "delivery": "deliver", "delivered": "deliver", "refunded": "refund", "charged": "charge"}


def _stem(w: str) -> str:
    w = SYN.get(w, w)
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            return SYN.get(w[: -len(suf)], w[: -len(suf)])
    return w


def features(text: str) -> Counter:
    words = [_stem(w) for w in re.findall(r"[a-z]+", text.lower()) if w not in STOP]
    f: Counter = Counter()
    for w in words:
        f["w:" + w] += 1.0
        padded = f"#{w}#"
        for i in range(len(padded) - 2):
            f["c:" + padded[i : i + 3]] += 0.3
    for a, b in zip(words, words[1:]):
        f[f"b:{a}_{b}"] += 0.7
    return f


def _slot(feat: str) -> int:
    return zlib.crc32(feat.encode()) % DIM


class Vectorizer:
    def __init__(self, idf: dict[str, float] | None = None, default_idf: float = 1.0) -> None:
        self.idf = idf or {}
        self.default_idf = default_idf

    @classmethod
    def fit(cls, texts: Iterable[str]) -> "Vectorizer":
        texts = list(texts)
        df: Counter = Counter()
        for t in texts:
            df.update(set(features(t)))
        n = len(texts)
        idf = {k: math.log((1 + n) / (1 + v)) + 1 for k, v in df.items()}
        return cls(idf, math.log(1 + n) + 1)

    def transform(self, texts: Iterable[str]) -> np.ndarray:
        rows = []
        for t in texts:
            v = np.zeros(DIM, dtype=np.float32)
            for k, tf in features(t).items():
                v[_slot(k)] += tf * self.idf.get(k, self.default_idf)
            n = np.linalg.norm(v)
            rows.append(v / n if n else v)
        return np.stack(rows) if rows else np.zeros((0, DIM), dtype=np.float32)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps({"idf": self.idf, "default": self.default_idf}), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Vectorizer":
        d = json.loads(path.read_text(encoding="utf-8"))
        return cls(d["idf"], d["default"])
