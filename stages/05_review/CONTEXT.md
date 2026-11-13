# 05_review: the human check, as a screen

One job: show the person only what they must decide next, and take their decision in one click.

## Inputs
- Working (this run): the session's live decisions (`app/state.py`), fed by `data/state/decisions.json` and the replay stream
- Reference (every run): `_shared/design-tokens.md`, `_templates/decision-card.md`

Do NOT load: per-message inferences (only the card's evidence), dashboards, charts.

## Process
1. `GET /` renders the Decision Stream: one line of what the agent handled alone, then 3-5 cards ranked by score.
2. Each card: title, why it is here, the drafted actions, replies (EN / AR, editable), evidence on demand, and three buttons: **Approve**, **Edit**, **Not this**.
3. New messages arrive over SSE (`/events`); a card's count and rank update in place; a new spike adds a card marked "agent-initiated".
4. No chat box. Free text appears only inside "Not this" (optional reason) and the reply editors.

## Outputs
- the person's decision, posted to stage 06 (`POST /cards/{id}/approve | edit | reject | answer`)

## Check
A person who has never seen it decides three cards in under 60 seconds without being told how.
