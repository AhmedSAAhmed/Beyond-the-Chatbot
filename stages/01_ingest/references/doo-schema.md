# DOO-shaped message schema

Mirrors the resources in DOO's public REST API and webhooks (Developers Hub: inboxes, contacts, conversations, messages, custom attributes), so the inbound webhook in `app/main.py` (`POST /webhooks/doo`) can take the same shape.

| field | type | notes |
|---|---|---|
| `id` | str | message id |
| `conversation_id` | str | one opener per conversation in this sample |
| `contact_id` | str | stable per author |
| `inbox` / `channel` | str | `twitter`, `app_review`, `whatsapp`, `email`, `webchat` |
| `lang_hint` | str | source language; stage 02 detects the real one |
| `ts` | ISO-8601 | real tweet time; re-timed for Arabic reviews |
| `window` | `shift` \| `baseline` | baseline is used only to measure lift |
| `text` | str | customer text, handles stripped, links replaced by `[link]` |
| `source`, `source_ref` | str | dataset + row/tweet id, so every message is traceable |

Contacts (`contacts.json`): `tier` (`vip` / `loyal` / `standard`) and `orders` (`order_id`, `amount_sar`, `status`). These are **simulated**, generated deterministically from the contact id, because no public dataset ships an order system.
