# Recovery paths: when the agent guessed wrong

| What was wrong | What the person does | What the system does |
|---|---|---|
| The issue itself | Not this -> picks one of the card's alternatives (or types the right issue) | Reclassifies the card's messages to the chosen intent, records a correction per message, re-runs 04 for that group, re-ranks the stream |
| The action | Edit -> changes amounts, removes an action, rewrites the reply | Executes the edited version; stores the before/after as a correction for 04 |
| Not sure | Answers the question card | Uses the answer as the hypothesis, then drafts the actions |
| Approved by mistake | Undo (30 s) | Reverses every action and logs it |
| Too late to undo | "Compensate" in the log | Runs the reverse actions as new, approved actions |
| Not now | Snooze | Hides the card for 30 minutes of shift time; it comes back if it grows |
| A message tried to instruct the agent | nothing | The message is flagged `injection`, kept out of drafts, and shown on the card |
