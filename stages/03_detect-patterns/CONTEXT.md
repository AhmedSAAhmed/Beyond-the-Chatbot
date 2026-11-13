# 03_detect-patterns: group similar problems and measure what is spiking

One job: turn per-message inferences into clusters of the same problem, each with size, lift against the baseline, risk and money at stake.

## Inputs
- Working (this run): `data/state/inferences.jsonl`
- Reference (every run): `stages/03_detect-patterns/references/clustering.md`
- Reference (every run): `_shared/intent-taxonomy.md`

Do NOT load: the prompts of 02 or 04, contact orders beyond the counts this stage needs.

## Process
1. Vectorise each message's normalised `issue` phrase (local TF-IDF, `app/pipeline/vectors.py`).
2. Within each intent, cluster shift messages greedily by cosine similarity (threshold in `clustering.md`).
3. Count each baseline message for the cluster of its nearest shift neighbour (or none), then lift = share in shift / share in baseline.
4. Score each cluster: impact x urgency x novelty (formula in `clustering.md`).
5. Offline: `python _tools/run_pipeline.py --stage 03`.

## Outputs
- `data/state/clusters.json`, `data/state/vectorizer.json` (the fitted IDF table the live path reuses)

## Check
`python -m pytest tests/test_patterns.py`: every cluster has size >= 1, a finite lift and a score, and no message is in two clusters.
