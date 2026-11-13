# Decision Stream (DOO challenge): agent workspace

A non-chat, non-dashboard interface for a CX supervisor: it reads every inbound message, infers intent, finds what is spiking, and puts the 3-5 decisions that need a human on one screen, each with a drafted action that waits for approval.

## Where things live

| Folder | What it holds |
|---|---|
| [CONTEXT.md](CONTEXT.md) | the pipeline on one screen: read this second |
| `stages/` | the agent pipeline, in execution order; each `CONTEXT.md` is that step's contract, `references/` holds its prompt |
| `_shared/` | factory: taxonomy, action catalog, policies, brand voice, design tokens (stable across runs) |
| `_templates/` | blank starters: decision card, correction |
| `_tools/` | offline scripts: build dataset, run pipeline, eval, link check |
| `app/` | FastAPI runtime that executes stages 02-06 live and serves the UI |
| `data/` | `sample/` real messages (committed), `state/` pipeline outputs, `eval/` labelled set |
| `docs/` | architecture, failure test, thesis |
| `tests/` | pytest suite |

## Route by task

| If | Go to | Then stop at |
|---|---|---|
| rebuilding data from raw sources | [01_ingest](stages/01_ingest/CONTEXT.md) | its check |
| changing how messages are classified | [02_infer-intent](stages/02_infer-intent/CONTEXT.md) | `_tools/eval_intents.py` accuracy |
| changing clustering / spike detection | [03_detect-patterns](stages/03_detect-patterns/CONTEXT.md) | its check |
| changing what the agent proposes | [04_propose-decision](stages/04_propose-decision/CONTEXT.md) | policy gate tests |
| changing the screen | [05_review](stages/05_review/CONTEXT.md) | a person decides 3 cards in < 60s |
| changing execution, undo or learning | [06_act-and-learn](stages/06_act-and-learn/CONTEXT.md) | `tests/test_failure_recovery.py` |
| asked for status | `data/state/` files and any `check.md` | report what exists |

## The one rule

Nothing reaches a customer or a system until a person approves it. Code enforces this, not the prompt.

## Deliberate break of the ICM method

ICM is built for sequential, checked work, not multi-user serving. So ICM governs the contracts, prompts, checks and the offline run, and `app/` is the runtime that loads those same contract files (`app/contracts.py`). The prompts live in exactly one place: `stages/*/references/`.
