"""Check for stage 02: run the live classifier on the Bitext labelled sample.

    python _tools/eval_intents.py [--limit N]

Writes data/eval/report.md; its first line is `pass` (accuracy >= 0.85) or `fail: <why>`.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.llm import usage  # noqa: E402
from app.pipeline.infer import classify_batch  # noqa: E402

BATCH = 15
THRESHOLD = 0.85


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    rows = [json.loads(line) for line in (ROOT / "data/eval/bitext_eval.jsonl").open(encoding="utf-8")]
    if args.limit:
        rows = rows[: args.limit]
    msgs = [{"id": f"e{i}", "text": r["text"], "lang_hint": "en"} for i, r in enumerate(rows)]
    batches = [msgs[i : i + BATCH] for i in range(0, len(msgs), BATCH)]
    preds: dict[str, str] = {}
    with ThreadPoolExecutor(args.workers) as ex:
        for out in ex.map(classify_batch, batches):
            preds.update({o["id"]: o["intent"] for o in out})

    per = defaultdict(lambda: [0, 0])
    confusions: Counter = Counter()
    for i, r in enumerate(rows):
        p = preds.get(f"e{i}", "other")
        per[r["intent"]][1] += 1
        if p == r["intent"]:
            per[r["intent"]][0] += 1
        else:
            confusions[(r["intent"], p)] += 1
    correct = sum(v[0] for v in per.values())
    acc = correct / len(rows)
    verdict = "pass" if acc >= THRESHOLD else f"fail: accuracy {acc:.3f} < {THRESHOLD}"
    lines = [
        verdict,
        "",
        "# Stage 02 intent accuracy on Bitext",
        "",
        f"- Examples: {len(rows)} across {len(per)} intents (stratified sample, seed 7)",
        f"- Model calls by provider: {dict(usage) or 'all served from cache'}",
        f"- Accuracy: **{acc:.1%}** ({correct}/{len(rows)})",
        "- Classifier: `app/pipeline/infer.py` with the prompt in `stages/02_infer-intent/references/prompt.md`, unchanged from production.",
        "- The model chooses from all 38 intents (Bitext 27 + 11 real-world), so a pick from the extra 11 counts as wrong.",
        "",
        "| intent | correct |",
        "|---|---|",
    ]
    lines += [f"| {k} | {v[0]}/{v[1]} |" for k, v in sorted(per.items())]
    lines += ["", "Most common confusions (true -> predicted):", ""]
    lines += [f"- {a} -> {b}: {n}" for (a, b), n in confusions.most_common(10)]
    (ROOT / "data/eval/report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(verdict, f"{acc:.3f}")
    return 0 if acc >= THRESHOLD else 1


if __name__ == "__main__":
    sys.exit(main())
