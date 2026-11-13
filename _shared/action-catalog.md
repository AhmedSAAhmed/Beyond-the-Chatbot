# Action catalog

The agent may propose only these actions. Anything else in a model response is dropped by `app/policy.py`. Every action is a draft until a person approves it, and every executed action has an undo.

| type | params | what executing does (simulated system of record) | undo |
|---|---|---|---|
| send_reply_batch | `reply_en`, `reply_ar` | sends the reply to every conversation on the card, in each customer's language | sends nothing further; marks replies retracted |
| issue_refund | `amount_sar_each`, `reason` | refunds each affected customer's most recent order up to the amount | reverses the refund |
| issue_credit | `amount_sar_each`, `reason` | adds goodwill store credit | removes the credit |
| reship_item | `reason` | creates a free replacement shipment | cancels the shipment |
| escalate_to_team | `team`, `note` | opens a ticket for `logistics`, `payments`, `tech`, `trust_safety` or `catalog` | closes the ticket |
| update_knowledge | `title`, `answer_en`, `answer_ar` | adds an answer to the AI agent's knowledge (CTRL) so the same question auto-resolves next time | removes the answer |
| tag_conversations | `label` | labels the conversations for reporting | removes the label |
