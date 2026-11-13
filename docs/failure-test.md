# Failure test: when the interface guesses wrong

**Scenario.** The agent groups a set of messages and proposes the wrong reading. Then, when asked to re-draft, the model over-reaches: it proposes a SAR 9,000 refund per customer and an action that does not exist ("wire money abroad").

**What the supervisor sees and does**

1. The card says what the agent believes, how sure it is, and shows the evidence (the real messages, with their source ids). The supervisor opens the evidence and sees that it is wrong.
2. **Not this.** The card offers the agent's two next-best readings, each with a reason, plus "something else" for a few typed words. One click.
3. The card re-draws: new title, new actions, new replies in English and Arabic, and a green line, *"Corrected by you: X → Y. N messages re-labelled."* Every message on the card moves to the corrected intent, and the correction is added to the inference prompt for every new message in this session.
4. The over-reach never reaches the screen as-is: the policy gate turns the SAR 9,000 refund into an escalation to payments, drops the unknown action, and says so on the card ("Refund SAR 9000 is above the SAR 500 cap: changed to escalation…").
5. The supervisor edits the English reply and approves. The card collapses into a receipt (replies by language, refunds, tickets, a sha256 digest of exactly what was approved).
6. They change their mind: **Undo** within 30 seconds reverses everything. After 30 seconds, Undo becomes a *compensation*, recorded as such in the audit log.

**When the agent is unsure in the first place**, it does not guess: below 60% confidence the card has no Approve button at all; it asks one question ("Billing error or fraud?") and drafts only from the answer.

**Automated.** `tests/test_failure_recovery.py` drives all of the above through the HTTP app with the model stubbed to return the bad draft:

```bash
python -m pytest tests/test_failure_recovery.py -q
```

| Step | Assertion |
|---|---|
| Not this | card shows "Corrected by you"; hypothesis changed; correction stored; all messages re-labelled |
| Gate | no `wire_money_abroad`; no refund over SAR 500; a policy note explains the change |
| Approve | receipt and Undo shown; the edit is recorded (`edited == ["reply_en"]`) |
| Undo | card is open again; audit log reads `undo, approve, reject` |
| Late undo | logged as `compensate` |
| Low confidence | question card has no Approve; answering it produces one |
| Injection | "Ignore all previous instructions…" is flagged even if the model misses it |
