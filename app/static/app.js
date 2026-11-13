// Decision Stream client: live updates over SSE, small interactions. No framework.
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));

  // nav border on scroll
  const nav = $("#nav");
  addEventListener("scroll", () => nav && nav.classList.toggle("scrolled", scrollY > 4), { passive: true });

  // ---- toasts ----
  const toast = (text) => {
    const box = $("#toasts");
    if (!box || !text) return;
    const t = document.createElement("div");
    t.className = "toast";
    t.textContent = text;
    box.appendChild(t);
    setTimeout(() => t.remove(), 5200);
  };

  // ---- card interactions (delegated, survive htmx swaps) ----
  document.addEventListener("click", (e) => {
    const tab = e.target.closest(".tab");
    if (tab) {
      const card = tab.closest(".card");
      $$(".tab", card).forEach((b) => b.setAttribute("aria-selected", b === tab ? "true" : "false"));
      $$(".reply", card).forEach((p) => p.classList.toggle("on", p.dataset.panel === tab.dataset.tab));
      return;
    }
    const edit = e.target.closest("[data-edit]");
    if (edit) {
      const card = edit.closest(".card");
      card.classList.toggle("editing");
      edit.textContent = card.classList.contains("editing") ? "Done editing" : "Edit";
      const ta = $(".reply.on textarea", card);
      if (ta && card.classList.contains("editing")) ta.focus();
      return;
    }
    const nt = e.target.closest("[data-notthis]");
    if (nt) {
      const card = nt.closest(".card");
      card.classList.toggle("show-notthis");
      return;
    }
    const ex = e.target.closest("[data-ex]");
    if (ex) {
      const ta = $("#inbound-text");
      ta.value = ex.dataset.ex;
      ta.focus();
      return;
    }
    if (e.target.closest("#fab")) {
      const d = $("#drawer");
      const open = d.classList.toggle("open");
      $("#fab").setAttribute("aria-expanded", String(open));
      $("#fab").textContent = open ? "Close" : "Send a customer message";
      if (open) $("#inbound-text").focus();
      return;
    }
    if (e.target.closest("[data-open-log]")) {
      $("#log").classList.add("open");
      document.body.dispatchEvent(new Event("load-log"));
      return;
    }
    if (e.target.closest("[data-close-log]")) $("#log").classList.remove("open");
  });

  // typing into the custom "something else" field selects that radio
  document.addEventListener("input", (e) => {
    if (e.target.name === "custom") {
      const r = e.target.closest(".alt").querySelector("input[type=radio]");
      if (r) r.checked = true;
    }
    if (e.target.tagName === "TEXTAREA") autosize(e.target);
  });

  const autosize = (ta) => {
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight + 2, 320) + "px";
  };
  const initAutosize = (root = document) => $$(".reply textarea", root).forEach((ta) => {
    const p = ta.closest(".reply");
    const wasOff = !p.classList.contains("on");
    if (wasOff) p.classList.add("on");
    autosize(ta);
    if (wasOff) p.classList.remove("on");
  });

  // ---- undo countdown ----
  setInterval(() => {
    const now = Date.now() / 1000;
    $$(".undo-timer").forEach((el) => {
      const left = Math.round(parseFloat(el.dataset.until) - now);
      el.textContent = left > 0 ? `undo · ${left}s` : "undo window closed · compensate";
    });
  }, 500);

  // ---- FLIP re-order of open cards ----
  const reorder = (order) => {
    const box = $("#cards");
    if (!box) return;
    const cards = $$(".card[data-status=open]", box);
    if (cards.length < 2) return;
    const current = cards.map((c) => c.dataset.card);
    const wanted = order.filter((id) => current.includes(id));
    if (wanted.join() === current.filter((id) => wanted.includes(id)).join()) return;
    if ($(".card.editing, .card.show-notthis", box) || box.contains(document.activeElement)) return; // never move under the user's hands
    const first = new Map(cards.map((c) => [c, c.getBoundingClientRect().top]));
    const anchor = cards[0].previousElementSibling;
    wanted.slice().reverse().forEach((id) => {
      const el = $(`#card-${CSS.escape(id)}`);
      if (el) anchor ? anchor.after(el) : box.prepend(el);
    });
    cards.forEach((c) => {
      const dy = first.get(c) - c.getBoundingClientRect().top;
      if (!dy) return;
      c.animate([{ transform: `translateY(${dy}px)` }, { transform: "none" }], { duration: 450, easing: "cubic-bezier(.2,.7,.2,1)" });
    });
  };

  const fetchCard = async (id) => {
    const r = await fetch(`/cards/${encodeURIComponent(id)}`);
    if (!r.ok) return;
    const html = await r.text();
    const box = $("#cards");
    const tpl = document.createElement("template");
    tpl.innerHTML = html.trim();
    const el = tpl.content.firstElementChild;
    if (!el || $(`#card-${CSS.escape(id)}`)) return;
    const empty = $("#empty");
    if (empty) empty.remove();
    box.prepend(el);
    if (window.htmx) htmx.process(el);
    initAutosize(el);
    el.animate([{ opacity: 0, transform: "translateY(-8px)" }, { opacity: 1, transform: "none" }], { duration: 400 });
  };

  // ---- live updates ----
  const root = $("#stream-root");
  if (root && window.EventSource) {
    let seenVersion = null;
    const es = new EventSource("/events");
    es.addEventListener("update", (ev) => {
      const p = JSON.parse(ev.data);
      const set = (id, v) => { const el = $(id); if (el && el.textContent !== String(v)) el.textContent = v; };
      set("#clock", p.now);
      set("#msg-count", p.messages.toLocaleString());
      set("#handled-count", p.handled.toLocaleString());
      set("#remaining", p.remaining);
      const q = $("#queued");
      if (q) { q.hidden = !p.queued; q.querySelector("span").textContent = p.queued; }
      const h1 = $("#hero-title");
      if (h1 && p.remaining === 0 && !h1.dataset.clear) {
        h1.dataset.clear = "1";
        h1.innerHTML = "The queue is clear.<br><em>Everything else is handled.</em>";
        if (!$("#empty")) {
          const e = document.createElement("div");
          e.className = "empty"; e.id = "empty";
          e.innerHTML = "<h2>Nothing needs you right now.</h2><p>The agent keeps answering what it can. When a new pattern appears it will draft the decision and bring it here.</p>";
          $("#cards").prepend(e);
        }
      } else if (h1 && p.remaining > 0 && h1.dataset.clear) {
        delete h1.dataset.clear;
        h1.innerHTML = `<span id="remaining">${p.remaining}</span> ${p.remaining === 1 ? "decision needs" : "decisions need"} you.<br><em>Everything else is handled.</em>`;
        const e = $("#empty"); if (e) e.remove();
      }
      for (const [id, c] of Object.entries(p.cards)) {
        const n = $(`#count-${CSS.escape(id)}`);
        if (n && n.textContent !== String(c.customers)) {
          n.textContent = c.customers;
          n.classList.remove("bump"); void n.offsetWidth; n.classList.add("bump");
        }
        const live = $(`#live-${CSS.escape(id)}`);
        if (live && c.live) { live.hidden = false; live.querySelector("span").textContent = c.live; }
        const sar = $(`#sar-${CSS.escape(id)}`);
        if (sar) sar.textContent = c.sar.toLocaleString();
        const card = $(`#card-${CSS.escape(id)}`);
        if (card) card.dataset.score = c.score;
      }
      p.order.forEach((id) => { if (!$(`#card-${CSS.escape(id)}`) && seenVersion !== null) fetchCard(id); });
      reorder(p.order);
      if (p.arrival) {
        const t = $("#ticker"), txt = $("#ticker-txt");
        const where = p.arrival.card && $(`#card-${CSS.escape(p.arrival.card)}`) ? " → joined a card" : "";
        txt.textContent = `${p.now} · ${p.arrival.lang.toUpperCase()} · ${p.arrival.intent.replace(/_/g, " ")}${where} · “${p.arrival.text}”`;
        txt.dir = p.arrival.lang === "ar" ? "auto" : "ltr";
        t.classList.remove("flash"); void t.offsetWidth; t.classList.add("flash");
      }
      if (seenVersion !== null) p.toasts.forEach((x) => toast(x.text));
      seenVersion = p.version;
    });
  }

  document.addEventListener("htmx:afterSwap", (e) => {
    initAutosize(e.target);
    if (e.target.id && e.target.id.startsWith("card-")) {
      e.target.animate([{ opacity: 0.4 }, { opacity: 1 }], { duration: 300 });
    }
  });
  document.addEventListener("htmx:responseError", (e) => {
    const s = e.detail.xhr.status;
    toast(s === 429 ? "Slow down: rate limit reached." : s === 503 ? "The model is busy. Try again in a moment." : "Something went wrong. Nothing was sent.");
  });
  document.addEventListener("DOMContentLoaded", () => initAutosize());
})();
