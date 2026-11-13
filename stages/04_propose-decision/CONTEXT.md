# 04_propose-decision: draft the decision a person should make

One job: for each cluster worth a person's attention, draft one decision card: what is happening, what to do (from the action catalog only), the replies in every customer language present, and what else it might be.

## Inputs
- Working (this run): `data/state/clusters.json` (one cluster + up to 6 representative messages per call)
- Reference (every run): `stages/04_propose-decision/references/prompt.md`
- Reference (every run): `_shared/action-catalog.md`, `_shared/policies.md`, `_shared/brand-voice.md`

Do NOT load: other clusters, raw datasets, the 02 prompt.

## Process
1. Pick the top clusters by score (not auto-handled; at most 8).
2. Call the model once per cluster, JSON only.
3. Run `app/policy.py` over the result: drop actions not in the catalog, apply caps, swap money for escalation where policy says so, record every change as a `policy_note` shown on the card.
4. Low confidence (< 0.6) turns the card into a question card: the person picks the hypothesis before any action is drafted.
5. Offline: `python _tools/run_pipeline.py --stage 04`.

## Outputs
- `data/state/decisions.json`

## Check
`python -m pytest tests/test_policy.py`: no decision contains an action outside the catalog or above a cap.
