# Execution plan: "Beyond the Chatbot" × DOO

Status: v2 (2026-11-13). Decisions taken: Decision Stream (A) · FastAPI + htmx · TWCS + Bitext, plus real Arabic reviews (SHEIN) · EN + AR · Navy tokens copied with permission · "built for DOO" framing · push to `main` · demo resets on restart · no LLM spend cap · no Loom.
Deadline: about 2026-12-16 (32 days left on the challenge page).

---

## 1. What the judges score, and what disqualifies

| Weight | Criterion | What that means for this build |
|---|---|---|
| 25 | Conceptual clarity | It must obviously beat DOO's own inbox + analytics digest for this one job |
| 25 | Technical depth | Real intent inference (LLM + embeddings + clustering), measured against labels, no hardcoded flows |
| 20 | Demo quality | The "wow" lands in the first 30 seconds of opening the live URL |
| 15 | Failure thinking | A wrong guess costs one click to fix, and the system learns from it |
| 15 | Future thesis | 300 words with a clear stance on post-chat UI |

Disqualified if: it's a chatbot in a wrapper, a dashboard with an "Ask AI" button, or there's no live demo.
Bonus: real dataset, an actual job.

**Design rule from this table:** no chat box and no charts grid anywhere in the main screen. Free text only appears as a fallback inside a card ("tell me what's wrong"), never as the main way in.

---

## 2. The workflow (recommended pick)

**Job: the CX supervisor's shift at a DOO customer** (a telecom like STC, or a delivery app like Jahez).
Today this person juggles DOO's Unified Inbox, the Pulse/Analytics digest and the CTRL correction screen to work out what needs them. DOO's own site shows the gap: *"Duplicate-charge complaints are up 12%, worth a look"* is a sentence in a dashboard. The person still has to go and look, decide, and act.

**What we build: a "Decision Stream".** One screen holding 3 to 5 decision cards, ranked. Each card holds one decision:

```
┌───────────────────────────────────────────────────────────────┐
│ 37 customers double-charged after the 02:10 gateway retry      │  <- inferred situation
│ Billing · duplicate charge · 92% confidence · 4 VIPs · SLA 40m │  <- why it's here
│                                                               │
│ Proposed: refund 37 × SAR 89, send apology (EN 21 / AR 16)     │  <- action the agent drafted itself
│ ▸ evidence: 3 representative messages (expand)                │
│ ▸ draft replies (edit inline)                                 │
│                                                               │
│ [Approve all]   [Edit]   [Not this ▾]          undo for 30s    │
└───────────────────────────────────────────────────────────────┘
```

- **Shows only what the person must decide next.** Everything the agent handled alone collapses into a single line ("2,480 handled overnight, 71% with no human").
- **Acts on its own, with human review:** it spots a new cluster (a spike against baseline), drafts the batch action, the replies in the customer's language, and a CTRL/knowledge-base patch so it doesn't recur. Then it queues all of it as a card. Nothing runs until a person approves.
- **What it replaces:** a side-by-side view (`/replaces`) showing the inbox + analytics + chat it removes.

Alternatives, if you'd rather:
- **B. QA & coaching surface:** auto-score every conversation and surface only the coaching moments for a team lead.
- **C. Knowledge-gap fixer:** find where the AI agent handed off or failed and propose CTRL corrections as diffs to approve.

A is the strongest fit. It covers B and C as card types, so they become features rather than separate products.

---

## 3. Data (real, not lorem ipsum)

| Role | Source | Notes |
|---|---|---|
| Live stream (real customers) | **Customer Support on Twitter (TWCS)**: about 3M real tweets between customers and brands (telecom, airlines, delivery, retail) | Kaggle; check for a Hugging Face mirror. License CC BY-NC-SA 4.0, which is fine for a non-commercial demo but must be credited. Take a 3 to 5k conversation subset from telecom/delivery brands to match DOO's sectors |
| Evaluation ground truth | **Bitext customer-support dataset** (about 27k rows, 27 intents, labeled) | Gives a measured intent-accuracy number for "technical depth". Check its license |
| Systems of record | Simulated orders / payments / refunds tables, generated once and committed | Labeled "simulated" in the UI and README. Being honest here is worth more than pretending |
| Arabic | Open question (Q4) | DOO's signature is replying in the customer's language |

Normalize everything into a **DOO-shaped schema**: inbox → contact → conversation → message → custom attributes. That's the resource model DOO's public REST API and webhooks expose (Developers Hub). The prototype then reads as "drop-in for DOO" and not a toy.

---

## 4. Architecture snapshot: data → intent inference → surfaced decision → action

```
 DOO-style webhook  ─┐
 replay simulator   ─┴─► 01 ingest ─► 02 infer intent ─► 03 detect patterns ─► 04 propose decision ─► 05 human review ─► 06 act + learn
                         normalize     rules first,        embeddings +          closed action           Decision          execute on simulated
                         + dedupe      then LLM            online clustering,    catalog + policy        Stream UI         systems, audit log,
                         + language    structured output   spike vs baseline     gates + confidence      approve/edit/     undo window,
                                       (intent, urgency,                         + impact ranking        not-this          corrections → few-shot
                                       sentiment, entities)                                                                memory for stage 02/04
                                              ▲                                                                                       │
                                              └───────────────────────── learning loop (corrections) ─────────────────────────────────┘
```

**Inference is layered** (ECC `regex-vs-llm-structured-text` + `cost-aware-llm-pipeline`):
1. L0 rules: order IDs, amounts, language detection, PII masking. Free and instant.
2. L1 LLM classification with a strict Pydantic schema: Groq (fast, free tier) first, with fallback to OpenRouter / Gemini. Keys are already in `.env`.
3. L2 Gemini embeddings + incremental clustering, so emerging issues come from the data and not a hand-written list.
4. L3 decision synthesis: the LLM may only pick from a closed **action catalog** (refund, reply batch, escalate, KB patch, tag), and **policy gates** run in code (refund caps, VIP rules). The model proposes; code decides what's allowed.

**Ranking:** `score = impact (customers × value × VIP) × urgency (SLA, sentiment trend) × novelty`. Confidence decides the card's form: a **proposal** when confident, a **question** when not ("Billing error or fraud? [Billing] [Fraud]").

---

## 5. Failure path (wrong-guess recovery)

| The system got it wrong | The person does | The system does |
|---|---|---|
| Wrong intent / cluster | `Not this ▾` → "wrong issue" | Shows the next-best hypothesis in place, can split or merge the cluster, logs a correction |
| Right issue, wrong action | Edits the action or replies inline | Runs the edited version; the diff becomes a few-shot example |
| Low confidence | Answers a one-tap question card | Reclassifies the whole cluster from that answer |
| Approved by mistake | Undo within 30s, or a compensating action later | Reverses on the simulated systems and writes it to the audit log |
| Agent going off the rails | Pause switch | Stops drafting new actions; manual mode |
| Prompt injection in a customer message | Nothing (automatic) | Customer text is handled as data and never as instructions (ECC `agent-security-hardening`); the action catalog and policy gates block anything outside it |

Deliverable: `docs/failure-test.md` plus an automated test that feeds a deliberately misleading cluster and checks the recovery path end to end.

---

## 6. Stack: honest take on Gradio

| | **FastAPI + Jinja + HTMX + SSE** (recommended) | Gradio |
|---|---|---|
| Language | 100% Python, no JS build step | 100% Python |
| Looks like | Anything, so the Navy theme can be applied exactly | An ML demo; its building blocks are chat and dataframe widgets |
| DQ risk | Low | Real: it reads as "dashboard/chatbot" unless you fight its CSS |
| Live updates | SSE pushes new cards as messages arrive | Possible, but awkward |
| Render free (512 MB) | About 80 MB RAM | Heavier, slower cold start |

Rest of the stack: Python 3.12, Pydantic v2, SQLite (seeded at boot from committed data), `httpx` to OpenAI-compatible endpoints (Groq/OpenRouter), Tailwind CSS built once with the standalone CLI (no Node), pytest. No torch or local models, to fit in 512 MB.

---

## 7. Render free tier: constraints and mitigations (re-check limits at build time)

| Constraint | Mitigation |
|---|---|
| Spins down after about 15 min idle, cold start 30 to 60s, which hurts the "wow in 30s" | Keep-alive ping (GitHub Actions cron every 10 min, which stays inside 750 free hours/month) plus a static "waking up" splash |
| 512 MB RAM, 0.1 CPU | Precompute embeddings and clusters offline (ICM stages run as batch), commit the artifacts, and do only incremental inference live |
| Ephemeral disk | SQLite rebuilt from `data/sample/` on each boot; a "Reset demo" button; persistence optional (Q8) |
| Public URL with server-side LLM keys | Per-IP rate limit, daily token budget, cached responses for the scripted demo path |

---

## 8. Repo structure (ICM: the folder structure is the agent architecture)

```
Beyond-the-Chatbot/
├─ AGENTS.md                 L0: identity + routing table (<60 lines, holds no content)
├─ CLAUDE.md                 one line: @AGENTS.md
├─ CONTEXT.md                L1: the pipeline on one screen
├─ stages/                   the agent's pipeline. Each CONTEXT.md is the prompt contract the runtime loads
│  ├─ 01_ingest/             {CONTEXT.md, references/doo-schema.md}
│  ├─ 02_infer-intent/       {CONTEXT.md, references/intent-taxonomy.md, examples/}
│  ├─ 03_detect-patterns/    {CONTEXT.md, references/clustering.md}
│  ├─ 04_propose-decision/   {CONTEXT.md, references/action-catalog.md}
│  ├─ 05_review/             {CONTEXT.md}  the human check, i.e. the UI
│  └─ 06_act-and-learn/      {CONTEXT.md, references/undo-rules.md}
├─ _shared/                  factory: brand-voice.md (EN/AR), policies.md, design-tokens.md (Navy)
├─ _templates/               decision-card.md, correction.md
├─ _tools/                   links.py (from ICM), replay.py, seed.py, eval.py
├─ app/                      FastAPI runtime that runs the stages: main.py, routes/, services/, llm/, templates/, static/
├─ data/                     sample/ (committed subset), eval/, raw/ (gitignored)
├─ tests/
├─ docs/                     architecture.md, failure-test.md, thesis.md, replaces.png
├─ render.yaml  pyproject.toml  .env.example  README.md
└─ (gitignored) .env  .local-refs/{icm-architect,ecc}  .claude/
```

The deliberate ICM break is written into `AGENTS.md`: ICM says it is the wrong fit for multi-user serving. So ICM governs the **contracts, prompts, checks and the build workspace**, and FastAPI is the runtime that executes them. A judge can open `stages/02_infer-intent/CONTEXT.md` and read exactly what the model is told.

---

## 9. What we take from ECC (kept local in `.local-refs/ecc`, installed into a gitignored `.claude/`)

- **Rules:** `rules/common/*`, `rules/python/*` (style, security, testing, FastAPI)
- **Skills:** `fastapi-patterns`, `python-testing`, `tdd-workflow`, `verification-loop`, `regex-vs-llm-structured-text`, `cost-aware-llm-pipeline`, `operator-approval-loop` (hashed drafts + decision receipts, which is exactly our approval audit), `agent-security-hardening`, `ai-regression-testing`, `eval-harness`, `deployment-patterns`, `frontend-design-direction`, `ui-demo` (Playwright-recorded walkthrough for the Loom)
- **Agents:** `planner`, `architect`, `fastapi-reviewer`, `python-reviewer`, `security-reviewer`, `silent-failure-hunter`, `tdd-guide`

---

## 10. Phases (about 30 working days + buffer)

| Phase | Days | Output | Gate (check) |
|---|---|---|---|
| P0 Decisions + skeleton | 1–2 | Answers to section 12, `git init`, ICM skeleton, `links.py` passing, **"hello" deployed on Render** | Live URL opens |
| P1 Data | 3–6 | Dataset subset normalized to the DOO schema, simulated systems, eval set | `_tools/seed.py` builds the DB from a clean clone |
| P2 Inference engine | 7–12 | Stages 02–04 with structured output, fallback, caching | `_tools/eval.py` reports intent accuracy (target ≥ 85% on Bitext) |
| P3 Decision Stream UI | 13–18 | Navy-themed cards, approve/edit/not-this, SSE live arrivals, `/replaces` view | Real person: decides 3 cards in < 60s without explanation |
| P4 Proactive + learning + recovery | 19–22 | Spike detection → auto-drafted cards; correction memory; undo | Failure test passes |
| P5 Hardening | 23–26 | Tests, injection guard, rate limits, budget, keep-alive, security review | ECC security + silent-failure review is clean |
| P6 Deliverables | 27–30 | README, architecture snapshot, failure-test doc, thesis, Loom script + recording, submission notes | Clean clone runs; checklist complete |
| Buffer | 31–32 | | |

---

## 11. The first 30 seconds (demo script)

1. Open URL → "Good morning, Reem. **2,480 handled overnight. 3 need you.**" (no chat box, no charts)
2. Card 1: duplicate charges → one click on **Approve** → refunds + EN/AR replies go out, the counter ticks, the card collapses into the log.
3. Live: a new angry message arrives (replay) → card 2's count goes up and its rank changes in front of you.
4. Card 3 is wrong on purpose → **Not this** → the next hypothesis appears → corrected, "learned" toast.
5. Flip to `/replaces`: the inbox + dashboard + chatbot this replaces.

---

## 12. Open questions

1. **Workflow:** go with A (Decision Stream for CX supervisors), or B / C?
2. **Frontend:** FastAPI + HTMX (recommended), or do you want Gradio anyway?
3. **Dataset:** TWCS (real) for the live stream + Bitext for measured eval. OK? TWCS sits behind a Kaggle login; I'll look for a Hugging Face mirror first, otherwise you download it once.
4. **Arabic:** must the demo show Arabic replies? The LLM can reply in Arabic to Arabic messages, but a real Arabic source dataset is harder to find. Should I search for one, or is EN input + EN/AR output enough?
5. **Navy theme:** it's a paid Lexington Themes template ("Buy Navy"). Have you bought it? If not, I'll borrow only its design tokens (warm off-white `#F8F7F4`, ink `#1A1815`, 6px radius, Helvetica Neue/Switzer, a calm structured layout) and write our own markup, without copying their HTML or assets.
6. **DOO branding:** I suggest "Built for DOO" framing without using DOO's logo or copying their UI, so it doesn't look like an official DOO product. OK?
7. **GitHub:** is `AhmedSAAhmed/Beyond-the-Chatbot` empty? Do you want me to push to `main` directly, or work on a branch? (Commits will carry no Claude co-author line, as you asked.)
8. **Persistence:** OK for the demo to reset on each restart, or should approvals persist (needs a free external DB such as Turso/Supabase)?
9. **LLM budget:** any hard daily spend cap for the public demo? Default: Groq free tier + cached demo path, $0.
10. **Loom:** you record it; I write the script and a Playwright auto-run you can screen-capture. OK?
