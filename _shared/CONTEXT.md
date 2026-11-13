# _shared: the factory

Stable reference that constrains every run. Change these only on purpose; every stage reads only the files its contract lists.

| File | Used by | What it fixes |
|---|---|---|
| [intent-taxonomy.md](intent-taxonomy.md) | 02, 03 | the closed set of intents (Bitext 27 + 11 for real-world traffic) |
| [action-catalog.md](action-catalog.md) | 04, 06 | the only actions the agent may propose |
| [policies.md](policies.md) | 04, 06 | limits enforced in code (`app/policy.py`) |
| [brand-voice.md](brand-voice.md) | 04 | how replies sound, in English and Arabic |
| [design-tokens.md](design-tokens.md) | 05 | the Navy theme tokens used by `app/static/app.css` |
