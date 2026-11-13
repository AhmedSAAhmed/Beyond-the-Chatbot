"""Check for stage 04: no decision escapes the action catalog or the caps in _shared/policies.md."""
import json

from conftest import ROOT

from app import contracts
from app.policy import CREDIT_CAP, REFUND_CAP, gate


def d(*actions):
    return {"actions": list(actions), "reply_en": "x", "reply_ar": "y", "policy_notes": []}


def test_unknown_actions_are_dropped():
    out = gate(d({"type": "wire_money_abroad", "params": {}}), intent="get_refund", customers=3)
    assert {a["type"] for a in out["actions"]} == {"send_reply_batch"}
    assert any("not in the action catalog" in n for n in out["policy_notes"])


def test_refund_above_cap_becomes_escalation():
    out = gate(d({"type": "issue_refund", "params": {"amount_sar_each": 9000}}), intent="get_refund", customers=3)
    types = [a["type"] for a in out["actions"]]
    assert "issue_refund" not in types and "escalate_to_team" in types
    esc = next(a for a in out["actions"] if a["type"] == "escalate_to_team")
    assert esc["params"]["team"] == "payments"


def test_refund_never_exceeds_order_value():
    out = gate(d({"type": "issue_refund", "params": {"amount_sar_each": 400}}), intent="get_refund", customers=3, max_order_sar=120)
    refund = next(a for a in out["actions"] if a["type"] == "issue_refund")
    assert refund["params"]["amount_sar_each"] <= 120


def test_credit_is_capped():
    out = gate(d({"type": "issue_credit", "params": {"amount_sar_each": 900}}), intent="complaint", customers=3)
    credit = next(a for a in out["actions"] if a["type"] == "issue_credit")
    assert credit["params"]["amount_sar_each"] == CREDIT_CAP


def test_security_issues_never_get_money():
    out = gate(d({"type": "issue_refund", "params": {"amount_sar_each": 50}}), intent="account_security", customers=2)
    assert not any(a["type"] in {"issue_refund", "issue_credit"} for a in out["actions"])
    assert any(a["params"].get("team") == "trust_safety" for a in out["actions"])


def test_every_card_has_a_reply_action_first():
    out = gate(d({"type": "tag_conversations", "params": {"label": "x"}}), intent="complaint", customers=2)
    assert out["actions"][0]["type"] == "send_reply_batch"


def test_committed_decisions_obey_policy():
    decisions = json.loads((ROOT / "data/state/decisions.json").read_text(encoding="utf-8"))
    assert 3 <= len(decisions) <= 8
    allowed = contracts.catalog_types()
    for dec in decisions:
        assert dec["reply_en"] and dec["reply_ar"], dec["card_id"]
        for a in dec["actions"]:
            assert a["type"] in allowed
            if a["type"] == "issue_refund":
                assert a["params"]["amount_sar_each"] <= REFUND_CAP
            if a["type"] == "issue_credit":
                assert a["params"]["amount_sar_each"] <= CREDIT_CAP
