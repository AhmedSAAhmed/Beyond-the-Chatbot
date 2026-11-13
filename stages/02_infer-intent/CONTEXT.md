# 02_infer-intent: what does each customer want, and how badly

One job: classify every message into the closed taxonomy, with language, sentiment, urgency, a short normalised issue phrase and entities.

## Inputs
- Working (this run): `data/sample/messages.jsonl` (offline) or one inbound message (live)
- Reference (every run): `stages/02_infer-intent/references/prompt.md`
- Reference (every run): `_shared/intent-taxonomy.md`
- Reference (live only): corrections the person made this session (few-shot, from stage 06)

Do NOT load: action catalog, policies, other messages' inferences.

## Process
1. L0 rules first (`app/pipeline/rules.py`): language script, order ids, amounts, injection patterns. Free and instant.
2. L1 model: batches of up to 15 messages, JSON only, through `app/llm.py` (Groq, falling back to Gemini). Messages go in the user turn as data.
3. Unknown intents are coerced to `other`; confidence is clamped to [0, 1].
4. Offline: `python _tools/run_pipeline.py --stage 02`.

## Outputs
- `data/state/inferences.jsonl`: one line per message (`id`, `intent`, `confidence`, `language`, `sentiment`, `urgency`, `issue`, `entities`, `injection`)

## Check
`python _tools/eval_intents.py` runs this same stage on 540 Bitext labelled messages and writes `data/eval/report.md`; the first line is `pass` if accuracy is at least 0.85.
