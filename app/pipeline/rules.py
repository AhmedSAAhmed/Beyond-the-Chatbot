"""Stage 02, layer 0: deterministic signals that cost nothing and never hallucinate."""
from __future__ import annotations

import re

ARABIC = re.compile(r"[؀-ۿ]")
ORDER_ID = re.compile(r"\b(?:ORD-\d{6}|\d{3}-\d{7}-\d{7}|#\d{5,})\b")
AMOUNT = re.compile(r"(?:[$£€₹]|SAR|BHD|AED|Rs\.?)\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?(?:SAR|BHD|AED|ريال|دينار)", re.I)
INJECTION = re.compile(
    r"ignore (?:all |any |the )?(?:previous|prior|above) (?:instructions|prompts?)"
    r"|disregard (?:your|the) (?:instructions|rules)"
    r"|you are now|system prompt|developer mode|act as (?:an? )?(?:ai|admin|system)"
    r"|approve (?:a |the )?refund of|issue (?:me )?a refund of \d{4,}"
    r"|تجاهل (?:كل )?التعليمات",
    re.I,
)


def script_language(text: str) -> str | None:
    """'ar' when most letters are Arabic script; None means 'let the model decide'."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return None
    share = sum(bool(ARABIC.match(c)) for c in letters) / len(letters)
    return "ar" if share > 0.5 else None


def signals(text: str) -> dict:
    order = ORDER_ID.search(text)
    amount = AMOUNT.search(text)
    return {
        "language": script_language(text),
        "order_id": order.group(0) if order else None,
        "amount": amount.group(0) if amount else None,
        "injection": bool(INJECTION.search(text)),
    }
