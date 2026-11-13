"""Check for stage 01: the committed sample matches the DOO-shaped schema."""
import json

from conftest import ROOT

FIELDS = {"id", "conversation_id", "contact_id", "inbox", "channel", "lang_hint", "ts", "window", "text", "source", "source_ref"}


def load():
    return [json.loads(x) for x in (ROOT / "data/sample/messages.jsonl").open(encoding="utf-8")]


def test_schema_and_coverage():
    msgs = load()
    assert len(msgs) > 2000
    assert all(FIELDS <= set(m) for m in msgs)
    assert {m["window"] for m in msgs} == {"shift", "baseline"}
    assert {m["lang_hint"] for m in msgs} >= {"en", "ar"}
    assert len({m["id"] for m in msgs}) == len(msgs)


def test_every_message_is_traceable_to_its_source():
    for m in load():
        assert m["source"] in {"twcs", "shein_ar"}
        assert m["source_ref"]


def test_contacts_have_simulated_orders():
    contacts = json.loads((ROOT / "data/sample/contacts.json").read_text(encoding="utf-8"))
    ids = {m["contact_id"] for m in load()}
    assert ids <= set(contacts)
    sample = next(iter(contacts.values()))
    assert sample["tier"] in {"vip", "loyal", "standard"}
    assert sample["orders"][0]["amount_sar"] > 0
