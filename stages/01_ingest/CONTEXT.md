# 01_ingest: raw public datasets into DOO-shaped messages

One job: turn the three public datasets into one stream of messages in DOO's resource model (inbox, contact, conversation, message).

## Inputs
- Working (this run): `data/raw/twcs.csv`, `data/raw/shein_ar.parquet`, `data/raw/bitext.csv` (gitignored; download links in README)
- Reference (every run): `stages/01_ingest/references/doo-schema.md`

Do NOT load: anything under `data/state/`, other stages' references.

## Process
1. If a raw file is missing, stop and say which.
2. Run `python _tools/build_dataset.py`.
3. Shift = real Cyber Monday 2017 @AmazonHelp openers (12:00-24:00 UTC); baseline = a random sample of the prior 14 days. Arabic 1-2 star reviews are split between both windows and re-timed, because the source has no timestamps.

## Outputs
- `data/sample/messages.jsonl`, `data/sample/contacts.json` (contacts carry a *simulated* tier and orders)
- `data/eval/bitext_eval.jsonl` (20 labelled examples per Bitext intent)

## Check
`python -m pytest tests/test_data.py` confirms every message matches the schema and both windows and both languages are present.
