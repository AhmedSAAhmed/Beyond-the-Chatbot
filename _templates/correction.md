# Correction: one record per person-made fix

```
message_id: {id}
text: {customer text}
from_intent: {what the agent said}
to_intent: {what the person chose}
reason: {optional, typed by the person}
card_id: {card}
at: {ISO time}
```

Stage 02 renders the session's corrections as few-shot lines: `"{text}" -> {to_intent} (not {from_intent})`.
