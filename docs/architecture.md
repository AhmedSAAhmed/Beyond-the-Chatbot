# Architecture snapshot

```
 data                          intent inference                 surfaced decision                     action
 ───────────────────────────   ──────────────────────────────   ───────────────────────────────────   ─────────────────────────────
 TWCS @AmazonHelp tweets  ─┐   02 rules (L0)                    03 issue vectors, greedy clusters      06 policy gate (again)
 SHEIN Arabic reviews     ─┼─► script · order id · amount  ──►     within each intent             ──►     execute on simulated
 DOO webhook / drawer     ─┘   injection patterns                  lift vs 14-day baseline                 systems of record
 (inbox·contact·conv·msg)      02 model (L1): 38 intents,          score = impact × urgency × novelty      audit + sha256 receipt
                               language, sentiment, urgency,    04 draft: title, actions from           30 s undo / compensate
                               issue phrase, entities              catalog, EN + AR replies,          corrections → few-shot
                               (Groq → Gemini pool, cached)        alternatives, question             for the next inference
                                                                   policy gate in code
                                                                05 Decision Stream: 3–5 cards,
                                                                   approve / edit / not this
```

| Concern | Where | Why this way |
|---|---|---|
| Prompts and rules | `stages/*/references/`, `_shared/` | ICM: one home per fact; the runtime loads these files (`app/contracts.py`) so the repo is the spec |
| Offline run | `_tools/run_pipeline.py` | heavy work (3k classifications and the drafts) runs once; Render's free tier loads small JSON and rebuilds the vectors in under a second |
| Live path | `app/state.py: Engine.inbound` | a new message is classified by a real model call (about 1-3 s), vectorised locally and routed to its nearest neighbour's cluster |
| Per-visitor sandbox | `app/state.py: Session` | every judge sees the same shift from the start; nothing one visitor does leaks to another |
| Safety | `app/policy.py`, `app/pipeline/rules.py` | the model proposes, code disposes: catalog, caps, security rule, injection flag |
| Learning | `Engine.reject` → `Session.corrections` → `infer.corrections_block` | the person's correction is in the next inference prompt and re-labels similar messages |
| Grouping | `app/pipeline/vectors.py` | the LLM already normalises every message into an English issue phrase, so grouping is local TF-IDF: no second model, no quota (a Gemini embedding run hit the free daily cap at 900 of 2,916 texts, which is why) |
| Model access | `app/llm.py` | plain HTTPS to Groq and Gemini, a rotating pool across free quotas, a disk cache keyed by prompt hash |

Memory on Render: about 120 MB (numpy + 2,900 messages + their 1,024-dim float32 vectors).
