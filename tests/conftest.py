import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


FAKE_DRAFT = {
    "title": "Corrected reading of the issue",
    "situation": "Re-drafted after the supervisor's correction.",
    "hypothesis": "corrected hypothesis",
    "confidence": 0.9,
    "actions": [
        {"type": "send_reply_batch", "params": {}, "why": "answer everyone"},
        {"type": "issue_refund", "params": {"amount_sar_each": 9000}, "why": "model over-reaches"},
        {"type": "wire_money_abroad", "params": {}, "why": "not in catalog"},
    ],
    "reply_en": "Sorry about this. We are fixing it.",
    "reply_ar": "نعتذر عن ذلك، نعمل على حله.",
    "reply_other": {},
    "alternatives": [{"hypothesis": "something else", "intent": "complaint", "why": "fallback"}],
    "question": None,
}


@pytest.fixture()
def offline_models(monkeypatch):
    """No network: the model returns a fixed (deliberately over-reaching) draft and classification."""
    from app.pipeline import decide, infer

    monkeypatch.setattr(decide, "complete_json", lambda *a, **k: dict(FAKE_DRAFT))

    def fake_classify(system, user, **k):
        import json

        payload = json.loads(user.split("\n", 1)[1])
        return {"results": [{"id": m["id"], "intent": "delivery_problem", "confidence": 0.9, "language": "en", "sentiment": -2, "urgency": "high", "issue": "package not delivered", "entities": {}, "injection": False} for m in payload]}

    monkeypatch.setattr(infer, "complete_json", fake_classify)


@pytest.fixture()
def client(offline_models):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c
