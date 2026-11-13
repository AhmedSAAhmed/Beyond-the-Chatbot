"""FastAPI runtime: serves stage 05 (the Decision Stream) and runs stages 02-04 and 06 live."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from . import act, contracts
from .config import ROOT, settings
from .llm import LLMError, usage
from .state import Base, Engine, Session

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("app")

COOKIE = "ds_sid"
REPO = "https://github.com/AhmedSAAhmed/Beyond-the-Chatbot/blob/main/"
engine: Engine | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global engine
    engine = Engine(Base())
    act.db()
    log.info("loaded %d messages, %d cards, live LLM=%s", len(engine.base.msgs), len(engine.base.decisions), settings.live_llm)
    yield


templates = Jinja2Templates(directory=str(ROOT / "app" / "templates"))
LANG_NAMES = {"en": "English", "ar": "العربية", "fr": "Français", "es": "Español", "de": "Deutsch", "it": "Italiano", "hi": "Hindi", "pt": "Português"}
ACTION_LABEL = {
    "send_reply_batch": "Reply to every customer on this card",
    "issue_refund": "Refund",
    "issue_credit": "Store credit",
    "reship_item": "Ship a free replacement",
    "escalate_to_team": "Open a ticket for",
    "update_knowledge": "Teach the AI agent",
    "tag_conversations": "Tag conversations",
}
templates.env.globals.update(LANG_NAMES=LANG_NAMES, ACTION_LABEL=ACTION_LABEL, REPO=REPO, now=time.time)
templates.env.filters["fmt"] = lambda n: f"{int(round(n)):,}"
templates.env.filters["pct"] = lambda x: f"{round(float(x) * 100)}%"
templates.env.filters["human"] = lambda s: str(s).replace("_", " ")


def create_app() -> FastAPI:
    app = FastAPI(title="Decision Stream", lifespan=lifespan, docs_url="/api/docs", redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(ROOT / "app" / "static")), name="static")
    register(app)
    return app


# ---- helpers -----------------------------------------------------------------------------------
def eng() -> Engine:
    assert engine is not None
    return engine


def sess(request: Request) -> Session:
    return eng().session(request.cookies.get(COOKIE))


def with_cookie(resp: Response, s: Session) -> Response:
    resp.set_cookie(COOKIE, s.id, max_age=60 * 60 * 6, httponly=True, samesite="lax")
    return resp


_hits: dict[str, deque] = defaultdict(deque)


def rate_limited(request: Request, per_hour: int) -> bool:
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    q, now = _hits[ip], time.time()
    while q and q[0] < now - 3600:
        q.popleft()
    if len(q) >= per_hour:
        return True
    q.append(now)
    return False


def render_card(request: Request, s: Session, cid: str) -> HTMLResponse:
    c = eng().card(s, cid)
    if c is None:
        return HTMLResponse("")
    return with_cookie(templates.TemplateResponse(request, "_card.html", {"c": c, "s": s}), s)


def stream_context(s: Session) -> dict[str, Any]:
    view = eng().cards(s)
    return {"s": s, "v": view, "eval": eng().base.eval_report, "live": settings.live_llm}


class DooMessage(BaseModel):
    """Subset of a DOO 'message_created' webhook payload."""

    content: str = Field(min_length=2, max_length=600)
    channel: str = Field(default="whatsapp", max_length=20)
    contact_id: str | None = Field(default=None, max_length=64)


# ---- routes ------------------------------------------------------------------------------------
def register(app: FastAPI) -> None:
    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True, "cards": len(eng().base.decisions), "sessions": len(eng().sessions)}

    @app.get("/", response_class=HTMLResponse)
    def stream(request: Request) -> Response:
        s = sess(request)
        return with_cookie(templates.TemplateResponse(request, "stream.html", stream_context(s)), s)

    @app.get("/fragment/stream", response_class=HTMLResponse)
    def fragment(request: Request) -> Response:
        s = sess(request)
        return with_cookie(templates.TemplateResponse(request, "_stream.html", stream_context(s)), s)

    @app.post("/reset")
    def reset(request: Request) -> Response:
        s = eng().session(None)
        return with_cookie(RedirectResponse("/", status_code=303), s)

    @app.get("/events")
    async def events(request: Request) -> EventSourceResponse:
        s = sess(request)

        async def gen():
            last_arrived, last_version = -1, -1
            while not await request.is_disconnected():
                arrived = eng().arrived(s)
                if arrived != last_arrived or s.version != last_version:
                    view = eng().cards(s)
                    payload = {
                        "arrived": arrived,
                        "version": s.version,
                        "now": view["now"],
                        "messages": view["messages"],
                        "handled": view["handled_total"],
                        "remaining": view["remaining"],
                        "queued": view["queued"],
                        "cards": {c["id"]: {"customers": c["stats"]["customers"], "live": c["live_count"], "score": c["score"], "vip": c["stats"]["vip"], "sar": c["stats"]["sar_at_risk"]} for c in view["open"]},
                        "order": [c["id"] for c in view["open"]],
                        "toasts": [t for t in s.toasts if t["v"] > last_version],
                    }
                    if arrived != last_arrived and last_arrived >= 0 and arrived > 0:
                        mid = eng().base.tail[arrived - 1]
                        m, inf = eng().base.msgs[mid], eng().base.infs[mid]
                        payload["arrival"] = {"text": m["text"][:140], "lang": inf["language"], "intent": inf["intent"], "card": eng().base.cluster_of.get(mid)}
                    last_arrived, last_version = arrived, s.version
                    yield {"event": "update", "data": json.dumps(payload, ensure_ascii=False)}
                await asyncio.sleep(1.0)

        return EventSourceResponse(gen(), ping=15)

    @app.get("/cards/{cid}", response_class=HTMLResponse)
    def get_card(request: Request, cid: str) -> Response:
        return render_card(request, sess(request), cid)

    @app.post("/cards/{cid}/approve", response_class=HTMLResponse)
    async def approve(request: Request, cid: str) -> Response:
        s = sess(request)
        form = await request.form()
        edits = {
            "reply_en": form.get("reply_en"),
            "reply_ar": form.get("reply_ar"),
            "keep": form.getlist("keep") if form.get("edited") == "1" else None,
        }
        edits.update({k: form.get(k) for k in form.keys() if k.startswith("amount_")})
        if eng().card(s, cid) is None:
            raise HTTPException(404)
        await asyncio.to_thread(eng().approve, s, cid, edits)
        return render_card(request, s, cid)

    @app.post("/cards/{cid}/undo", response_class=HTMLResponse)
    def undo(request: Request, cid: str) -> Response:
        s = sess(request)
        eng().undo(s, cid)
        return render_card(request, s, cid)

    @app.post("/cards/{cid}/snooze", response_class=HTMLResponse)
    def snooze(request: Request, cid: str) -> Response:
        s = sess(request)
        eng().snooze(s, cid)
        return with_cookie(HTMLResponse(""), s)

    @app.post("/cards/{cid}/reject", response_class=HTMLResponse)
    def reject(request: Request, cid: str, alt: str = Form(""), custom: str = Form(""), reason: str = Form("")) -> Response:
        s = sess(request)
        idx = int(alt) if alt.isdigit() else None
        if idx is None and not custom.strip():
            raise HTTPException(422, "pick an alternative or describe the issue")
        eng().reject(s, cid, idx, custom[:200], reason[:200])
        return render_card(request, s, cid)

    @app.post("/cards/{cid}/answer", response_class=HTMLResponse)
    def answer(request: Request, cid: str, option: str = Form(...)) -> Response:
        s = sess(request)
        eng().answer(s, cid, option[:120])
        return render_card(request, s, cid)

    @app.post("/inbound", response_class=HTMLResponse)
    def inbound(request: Request, text: str = Form(...), channel: str = Form("whatsapp")) -> Response:
        s = sess(request)
        if rate_limited(request, settings.inject_per_hour):
            return HTMLResponse('<div class="trace trace-err">Rate limit: try again later.</div>', status_code=429)
        text = text.strip()
        if len(text) < 2:
            return HTMLResponse('<div class="trace trace-err">Type a customer message first.</div>', status_code=422)
        try:
            trace = eng().inbound(s, text[:600], channel[:20])
        except LLMError as exc:
            log.warning("inbound failed: %s", exc)
            return HTMLResponse('<div class="trace trace-err">The model is busy (free-tier rate limit). Try again in a few seconds.</div>', status_code=503)
        return with_cookie(templates.TemplateResponse(request, "_trace.html", {"t": trace, "e": eng(), "s": s}), s)

    @app.post("/webhooks/doo")
    def doo_webhook(request: Request, body: DooMessage) -> JSONResponse:
        """DOO-shaped inbound webhook. Uses the caller's session cookie if present."""
        s = sess(request)
        if rate_limited(request, settings.inject_per_hour):
            raise HTTPException(429, "rate limited")
        try:
            trace = eng().inbound(s, body.content, body.channel)
        except LLMError as exc:
            raise HTTPException(503, "model busy") from exc
        return with_cookie(JSONResponse({k: v for k, v in trace.items() if k != "text"}), s)  # type: ignore[return-value]

    @app.get("/fragment/log", response_class=HTMLResponse)
    def audit_log(request: Request) -> Response:
        s = sess(request)
        return with_cookie(templates.TemplateResponse(request, "_log.html", {"rows": act.log(s.id), "s": s}), s)

    @app.get("/replaces", response_class=HTMLResponse)
    def replaces(request: Request) -> Response:
        s = sess(request)
        b = eng().base
        inbox = [b.msgs[i] | {"inf": b.infs[i]} for i in b.pre[-14:]][::-1]
        intents = {}
        for i in b.pre:
            k = b.infs[i]["intent"]
            intents[k] = intents.get(k, 0) + 1
        top = sorted(intents.items(), key=lambda x: -x[1])[:8]
        return with_cookie(templates.TemplateResponse(request, "replaces.html", {"inbox": inbox, "top": top, "total": len(b.pre), "s": s}), s)

    @app.get("/how", response_class=HTMLResponse)
    def how(request: Request) -> Response:
        s = sess(request)
        b = eng().base
        ctx = {
            "s": s,
            "n_msgs": len(b.msgs),
            "n_shift": len(b.pre) + len(b.tail),
            "n_ar": sum(1 for m in b.msgs.values() if m["source"] == "shein_ar"),
            "n_clusters": len(b.clusters),
            "n_cards": len(b.decisions),
            "n_intents": len(contracts.taxonomy()),
            "eval": b.eval_report,
            "usage": dict(usage),
            "thesis": (ROOT / "docs" / "thesis.md").read_text(encoding="utf-8") if (ROOT / "docs" / "thesis.md").exists() else "",
        }
        return with_cookie(templates.TemplateResponse(request, "how.html", ctx), s)


app = create_app()
