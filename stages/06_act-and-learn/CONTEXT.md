# 06_act-and-learn: execute what was approved, undo, and learn from corrections

One job: run approved actions against the (simulated) systems of record, keep them reversible, and turn every correction into something the next inference uses.

## Inputs
- Working (this run): the person's decision from stage 05
- Reference (every run): `_shared/action-catalog.md`, `_shared/policies.md`
- Reference (every run): `stages/06_act-and-learn/references/recovery.md`

Do NOT load: prompts of 02 and 04 (it passes corrections to them; it does not edit them).

## Process
1. Approve: re-run the policy gate, execute each action, write an audit record with a hash of exactly what was approved, start a 30-second undo window.
2. Undo: reverse each executed action, write a compensating audit record.
3. Not this: follow `references/recovery.md`.
4. Corrections become few-shot examples for stage 02 in this session, and move similar messages to the corrected intent.

## Outputs
- audit log and corrections (SQLite `data/state/runtime-<pid>.sqlite`, recreated on boot)

## Check
`python -m pytest tests/test_failure_recovery.py` drives a wrong card end to end: reject, re-rank, correct, undo.
