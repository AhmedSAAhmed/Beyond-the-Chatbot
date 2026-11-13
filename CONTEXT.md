# Pipeline: data -> intent inference -> surfaced decision -> action

| # | Stage | Reads | Writes | Check |
|---|---|---|---|---|
| 01 | [ingest](stages/01_ingest/CONTEXT.md) | `data/raw/*` | `data/sample/messages.jsonl`, `contacts.json` | counts printed, schema test |
| 02 | [infer-intent](stages/02_infer-intent/CONTEXT.md) | messages | `data/state/inferences.jsonl` | Bitext accuracy report |
| 03 | [detect-patterns](stages/03_detect-patterns/CONTEXT.md) | inferences | `data/state/clusters.json` | every cluster has lift + size |
| 04 | [propose-decision](stages/04_propose-decision/CONTEXT.md) | clusters, policies | `data/state/decisions.json` | policy gates pass |
| 05 | [review](stages/05_review/CONTEXT.md) | decisions (live) | person's approve / edit / not-this | **the human check** |
| 06 | [act-and-learn](stages/06_act-and-learn/CONTEXT.md) | approved decisions | audit log, corrections | undo + recovery tests |

Offline, `python _tools/run_pipeline.py` runs 02 to 04 over the committed sample. Live, `app/` runs 02 to 04 on every message that arrives (the replay stream, or a message sent to the inbound webhook) and serves 05 and 06.

Factory shared by every stage: [_shared/](_shared/CONTEXT.md).
