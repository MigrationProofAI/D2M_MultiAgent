"""CAD-DESIGN driver — the front half of the D2M-UNIFIED flow. D2M (:9100) is the one app the user
drives; a "design a ..." prompt in the D2M chat is orchestrated here by driving AgentCAD (:5005) as a
headless CAD BACKEND: start a design, poll to each human gate, fetch the 2D/3D images, approve/revise.
The gates are D2M chat turns (pending-state in web.py), so the whole chain — prompt → 2D → [approve] →
3D → [approve] → CAD+PLM → genesis → SAP → demand/MRP — is ONE D2M session.

AgentCAD backend contract (cadplm/app.py):
  POST /api/design/start {intent}     -> {runid, phase}
  GET  /status/<runid>                -> {events[], phase, released, design_id, slug, elapsed, error}
  POST /approve2d/<runid>             -> advance 2D gate -> build 3D
  POST /revise2d/<runid> {note}       -> redraft the 2D with the correction
  POST /approve/<runid>               -> release -> CAD + PLM
  GET  /file/<rel>                    -> the drawing/exploded PNG bytes (events carry drawing_url=/file/…)

Phases: designing -> awaiting_2d -> building3d -> awaiting_approval -> persisting -> released.
"""
import os
import re
import json
import time
import urllib.request

AGENTCAD_URL = os.getenv("AGENTCAD_URL", "http://127.0.0.1:5005").rstrip("/")

# A CAD-DESIGN prompt: "design a …", "cad a …", "model a …", "sketch a …". Kept distinct from genesis
# ("build this from the image/file"), planning ("run mrp"), and completion questions. No image attached.
_DESIGN_RE = re.compile(
    r"\b(design|cad|model|sketch|draw\s*up|come\s*up\s*with\s*a\s*design|create\s*a\s*design)\b", re.I)
# don't hijack a genesis/plan/completion phrasing that merely contains 'design'
_NOT_DESIGN = re.compile(r"\b(run\s*mrp|create\s*a?\s*demand|is\s*everything|genesis\s*from|from\s*the\s*(image|file)|\.xlsx)\b", re.I)


def is_cad_design(text: str, has_image: bool = False) -> bool:
    t = text or ""
    if has_image or _NOT_DESIGN.search(t):
        return False
    return bool(_DESIGN_RE.search(t))


def _post(path, body=None, timeout=30, retries=0, backoff=0.8):
    """POST JSON. On HTTP 409 (the worker briefly still holds the run lock right after a gate) retry a few
    times with backoff — the gate approvals hit a tiny race between phase=awaiting_* and the lock release."""
    last = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(AGENTCAD_URL + path, data=json.dumps(body or {}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 409 and attempt < retries:
                last = e
                time.sleep(backoff * (attempt + 1))
                continue
            raise
    raise last


def _get(path, timeout=30):
    with urllib.request.urlopen(AGENTCAD_URL + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_file(rel_or_url, timeout=30) -> bytes | None:
    """Pull an AgentCAD-served image (drawing/exploded PNG) as bytes, given a /file/… url."""
    url = rel_or_url if rel_or_url.startswith("http") else (AGENTCAD_URL + rel_or_url)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read()
    except Exception:
        return None


def start_design(intent: str, iters: int = 5) -> dict:
    return _post("/api/design/start", {"intent": intent, "iters": iters})


def status(runid: str) -> dict:
    return _get(f"/status/{runid}")


def approve_2d(runid: str) -> dict:
    return _post(f"/approve2d/{runid}", retries=8, backoff=0.8)      # tolerate the lock-release race


def revise_2d(runid: str, note: str) -> dict:
    return _post(f"/revise2d/{runid}", {"note": note}, retries=8, backoff=0.8)


def approve_release(runid: str) -> dict:
    return _post(f"/approve/{runid}", retries=8, backoff=0.8)


def poll_until(runid: str, targets, timeout=900, interval=3, on_progress=None) -> dict:
    """Poll /status until phase is in `targets` (or 'released'/error). Returns the final status.
    on_progress(stage_text) is called as new timeline stages appear, so the D2M turn can narrate."""
    seen = set()
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        try:
            s = status(runid)
        except Exception as e:
            time.sleep(interval)
            continue
        last = s
        if on_progress:
            for ev in s.get("events", []):
                k = (ev.get("stage"), ev.get("i"), ev.get("ts"))
                if k in seen or ev.get("stage") in ("stream",):
                    continue
                seen.add(k)
                try:                                  # narration must NEVER break the poll/flow
                    line = _stage_line(ev)
                    if line:
                        on_progress(line)
                except Exception:
                    pass
        ph = s.get("phase")
        if ph in targets or ph == "released" or s.get("error"):
            return s
        time.sleep(interval)
    last["_timeout"] = True
    return last


def _stage_line(ev: dict) -> str:
    # LAZY by stage — a dict literal would eval every f-string for every event, and e.g. cad_done.parts
    # is an int (len(int) crashes). Only the matched branch runs here.
    st = ev.get("stage")
    if st == "brief":
        p = ev.get("parts")
        n = len(p) if isinstance(p, (list, tuple)) else (p if isinstance(p, int) else 0)
        return f"Designer seeded the brief — {n} parts"
    if st == "iter":
        return f"Verified the 2D — iter {ev.get('i')}, score {ev.get('score')}"
    if st == "sheet":
        return f"Typed 2D sheet ready — plan + elevation + iso ({ev.get('parts')} parts)"
    if st == "draft_gate":
        return "2D drawing ready"
    if st == "vision":
        return "Reviewed the render, folded corrections in"
    if st == "design_complete":
        return "Built the 3D assembly"
    if st == "assembly_step":
        return f"Exported the assembly STEP ({ev.get('instances')} instances)"
    if st == "cad_done":
        return f"Coded into CAD — {ev.get('product_pn')}"
    if st == "plm_done":
        return f"Wrote PLM specs — {ev.get('product_plm')}"
    if st == "released":
        return "Released — digital thread committed"
    return ""                                          # unknown/noisy stages -> silent


def latest_image(status_obj: dict):
    """(url, kind) of the most recent design image in the timeline — the exploded 3D if present, else the
    latest 2D drawing. Returns (None, None) if none yet."""
    ev = status_obj.get("events") or []

    def last(pred):
        return next((e for e in reversed(ev) if pred(e)), None)
    built3d = last(lambda e: e.get("stage") in ("assembly_step", "design_complete"))
    e3d = last(lambda e: e.get("exploded_url"))
    if built3d and e3d:                              # 3D is built -> the assembly exploded (rotate view)
        return e3d.get("exploded_url"), "3D exploded"
    esheet = last(lambda e: e.get("stage") == "sheet" and e.get("drawing_url"))
    if esheet:                                       # the TYPED 2D SHEET is THE 2D at the gate (beats the iso)
        return esheet.get("drawing_url"), "2D sheet"
    if e3d:
        return e3d.get("exploded_url"), "3D exploded"
    edraw = last(lambda e: e.get("drawing_url"))
    if edraw:
        return edraw.get("drawing_url"), "2D drawing"
    astep = last(lambda e: e.get("stage") == "assembly_step" and e.get("url"))
    if astep:
        return astep.get("url"), "assembly"
    return None, None


def brief_of(status_obj: dict) -> dict:
    return next((e for e in (status_obj.get("events") or []) if e.get("stage") == "brief"), {}) or {}


# ---- the per-turn state machine (called from web.py's dispatch) --------------------------------
_AFFIRM = re.compile(r"^\s*(go\s*ahead|go|yes|yep|yeah|ok(ay)?|sure|proceed|confirm(ed)?|approve[d]?|"
                     r"looks?\s*good|lgtm|ship\s*it|do\s*it|commit|next|continue|perfect|great)\b[\s.!,]*$", re.I)
# an approval word embedded in a short natural phrase ("Ok approved", "yes approve it", "looks good approve")
_AFFIRM_WORD = re.compile(r"\b(approved?|lgtm|go\s*ahead|looks?\s*good|ship\s*it|confirm(ed)?|proceed)\b", re.I)
# a change/correction verb -> it's a revision, NOT an approval, even when it also says "approve"
_CHANGE_WORD = re.compile(r"\b(but|instead|change|make\s|add|remove|bigger|smaller|wider|narrower|revise|"
                          r"redo|swap|move|replace|increase|decrease|short(er|en)?|long(er)?|thin(ner)?|"
                          r"thick(er)?|taller|rotate|fix|without|except)\b", re.I)


# a phrase that OPENS with an approval word ("approved for cad and plm", "ok approved", "yes go ahead now")
_AFFIRM_START = re.compile(r"^\s*(ok(ay)?|yes|yep|yeah|sure|approved?|confirm(ed)?|go\s*ahead|proceed|"
                           r"looks?\s*good|lgtm|ship\s*it|perfect|great|do\s*it|please\s*(do|go|proceed))\b", re.I)


def _is_affirm(text) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _CHANGE_WORD.search(t):                         # any correction verb -> it's a revision, not approval
        return False
    if _AFFIRM.match(t) or _AFFIRM_START.match(t):     # bare "approve" OR "approved for cad and plm", etc.
        return True
    return len(t.split()) <= 4 and bool(_AFFIRM_WORD.search(t))


# ---- vague design reference -> resolve to the product the user is actually talking about ----
_DESIGN_FILLER = re.compile(r"\b(what|about|how|the|a|an|some|show|me|us|can|could|would|you|please|now|of|"
                            r"for|it|this|that|is|are|do|does|did|2d|3d|cad|design|designs|model|drawing|"
                            r"blueprint|concept|sketch|generate|create|make|produce|give|let|lets|we|i|need|"
                            r"want|see|view|look|at|to|and|on|in|with|please)\b", re.I)


def _is_vague_design(t: str) -> bool:
    """True if the message is a design REFERENCE with no product of its own ('what about the 2d design?')."""
    core = re.sub(r"[^\w\s]", " ", _DESIGN_FILLER.sub(" ", t or "")).split()
    return len(core) < 2


def resolve_design_intent(text: str, recent_user_texts) -> str:
    """A vague design reference has no subject of its own — resolve it to the most recent substantive product
    the user described (newest first), so we design THAT, not the literal question."""
    t = (text or "").strip()
    if not _is_vague_design(t):
        return t
    for cand in recent_user_texts:
        c = (cand or "").strip()
        if c and c != t and len(c.split()) >= 3 and not _is_vague_design(c) and not _is_affirm(c):
            return c
    return t


_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9,
           "sept": 9, "oct": 10, "nov": 11, "dec": 12, "january": 1, "february": 2, "march": 3,
           "april": 4, "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
           "november": 11, "december": 12}
_NM = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _parse_demand(low: str):
    """(quantity, period YYYYMM, period_to YYYYMM|None, human span) from a natural demand instruction like
    'a demand of 10 units for the FG in Aug 26' or 'demand 100 EA every month Jul to Dec 2026'."""
    qty = "100"
    m = re.search(r"(\d{1,6})\s*(?:units?|ea|pcs?|pieces?)\b", low) or re.search(r"demand\s+of\s+(\d{1,6})\b", low)
    if m:
        qty = m.group(1)
    y = re.search(r"\b(20\d{2})\b", low)
    yr = int(y.group(1)) if y else 2026                # demo landscape is 2026; a 2-digit year lands here too
    mons = [_MONTHS[x] for x in re.findall(
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|"
        r"august|september|october|november|december)\b", low)]
    if mons:
        period = f"{yr}{mons[0]:02d}"
        period_to = f"{yr}{mons[-1]:02d}" if len(mons) >= 2 and mons[-1] != mons[0] else None
    else:
        period, period_to = f"{yr}08", None
    span = f"{_NM[int(period[4:])]} {period[:4]}" + (f"–{_NM[int(period_to[4:])]} {period_to[:4]}" if period_to else "")
    return qty, period, period_to, span


def _img_asset(session, url, on_progress=None):
    """Fetch an AgentCAD image and evict it into the D2M session's assets/ — returns the asset ref."""
    b = fetch_file(url)
    if not b:
        return None
    return session.add_asset(b, "png")


def _card(title, subtitle, body):
    payload = {"kind": "card", "title": title, "subtitle": subtitle, "content": body}
    return f"Rendered '{title}'.\n@@DATA@@" + json.dumps(payload, ensure_ascii=False)


def drive_cad_stage(session, pending: dict | None, text: str, plant: str = "1710", on_progress=None) -> dict:
    """Advance the unified CAD→SAP flow by ONE D2M turn. Returns:
       {answer, pending, image_ref, cards, chain, intent}
    pending carries {stage, runid, design_id}. stage ∈ {awaiting_2d, awaiting_3d, awaiting_genesis,
    awaiting_plan}. web.py persists `pending` in st and renders answer/image/cards."""
    def prog(msg):
        if on_progress:
            on_progress(msg)

    sid = session.id
    chain, cards = [], []

    # ---------- NEW DESIGN: prompt -> 2D gate ----------
    if not pending:
        prog("🎨 starting the design — Designer → Drafter → Verifier (this takes a couple of minutes)…")
        r = start_design(text)
        runid = r.get("runid")
        chain.append({"agent": "designer", "kind": "reasoning", "text": "Designing from the prompt…"})
        s = poll_until(runid, ("awaiting_2d",), on_progress=prog)
        if s.get("error"):
            return {"answer": f"⚠️ Design failed: {s['error']}", "pending": None, "intent": "cad_design"}
        b = brief_of(s)
        url, kind = latest_image(s)
        ref = _img_asset(session, url) if url else None
        parts = b.get("parts") or []
        body = (f"<div style='font-family:Arial'><b>{len(parts)} parts</b>"
                + (f" · {b.get('design_type')}" if b.get('design_type') else "")
                + (f"<div style='color:#666;margin-top:6px'>{b.get('summary','')[:300]}</div>" if b.get('summary') else "")
                + (f"<div style='margin-top:8px'><img src='/api/sessions/{sid}/asset/{ref.split('/')[-1]}' style='max-width:420px;border:1px solid #ccc;border-radius:6px'/></div>" if ref else "")
                + "</div>")
        cards.append({"tool": "cad_2d", "result": _card("2D concept — " + (b.get("design_type") or "design"),
                                                         "review gate · nothing built yet", body)})
        chain.append({"agent": "verifier", "kind": "reasoning", "text": f"2D ready — {len(parts)} parts."})
        answer = (f"🎨 **2D concept ready** — {len(parts)} parts"
                  + (f" ({b.get('design_type')})" if b.get("design_type") else "") + ".\n\n"
                  "Review the drawing in the panel. **Approve** to build the 3D, or describe any changes.")
        return {"answer": answer, "pending": {"stage": "awaiting_2d", "runid": runid},
                "image_ref": ref, "cards": cards, "chain": chain, "intent": "cad_design"}

    stage, runid = pending.get("stage"), pending.get("runid")

    # ---------- 2D gate ----------
    if stage == "awaiting_2d":
        if not _is_affirm(text):                    # a correction -> redraft
            prog("🖊 applying your correction and re-drafting the 2D…")
            revise_2d(runid, text)
            s = poll_until(runid, ("awaiting_2d",), on_progress=prog)
            url, _ = latest_image(s)
            ref = _img_asset(session, url) if url else None
            body = (f"<div><img src='/api/sessions/{sid}/asset/{ref.split('/')[-1]}' style='max-width:420px;border:1px solid #ccc;border-radius:6px'/></div>" if ref else "re-drafted")
            cards.append({"tool": "cad_2d", "result": _card("2D concept — revised", "review gate", body)})
            return {"answer": "🖊 Re-drafted with your correction. **Approve** to build the 3D, or refine further.",
                    "pending": {"stage": "awaiting_2d", "runid": runid}, "image_ref": ref, "cards": cards, "intent": "cad_design"}
        prog("🔧 2D approved — Motion is building the 3D assembly…")
        approve_2d(runid)
        s = poll_until(runid, ("awaiting_approval",), on_progress=prog)
        if s.get("error"):
            return {"answer": f"⚠️ 3D build failed: {s['error']}", "pending": None, "intent": "cad_design"}
        astep = next((e for e in reversed(s.get("events") or []) if e.get("stage") == "assembly_step"), {})
        slug = s.get("slug") or ""
        # THE INTERACTIVE 3D: embed AgentCAD's live Three.js viewer (rotate · explode · home) via a SAME-ORIGIN
        # D2M proxy so it frames reliably. NO static 2D image on this turn — the 3D is the only visual, so the
        # "3D" card never shows a 2D still.
        viewer_url = f"/cadviewer/{slug}" if slug else ""
        iframe = (f"<iframe src='{viewer_url}' style='width:100%;height:520px;border:1px solid #E5DDCB;"
                  f"border-radius:8px;background:#F5F1E8' title='3D assembly — rotate, explode, home'></iframe>"
                  f"<div style='margin-top:6px'><a href='{viewer_url}' target='_blank' style='font-size:11px;"
                  f"color:#C8553D;font-family:ui-monospace,monospace'>open the 3D full-screen ↗</a></div>"
                  if viewer_url else "<div style='color:#b5722a'>3D viewer unavailable (no slug)</div>")
        body = (f"<div style='font-family:Arial'><b>{astep.get('instances', '')} instances</b>"
                + (f" · {astep.get('size_mm')} mm" if astep.get('size_mm') else "")
                + "<div style='color:#8A8578;font-size:11px;margin:4px 0 8px'>drag to rotate · explode · home — the live 3D assembly</div>"
                + iframe + "</div>")
        cards.append({"tool": "cad_3d", "result": _card("3D assembly (interactive)", "review gate · nothing written to SAP", body)})
        chain.append({"agent": "motion", "kind": "reasoning", "text": "Built the 3D assembly — interactive viewer."})
        return {"answer": "🔧 **3D assembly ready** — drag to rotate, explode, home it in the panel. **Approve** to create the CAD + PLM master data.",
                "pending": {"stage": "awaiting_3d", "runid": runid}, "image_ref": None, "cards": cards, "chain": chain, "intent": "cad_design"}

    # ---------- 3D gate -> release CAD + PLM -> genesis PREVIEW ----------
    if stage == "awaiting_3d":
        if not _is_affirm(text):
            return {"answer": "Type **approve** to create CAD + PLM, or restate the design to start over.",
                    "pending": pending, "intent": "cad_design"}
        prog("🗄 approved — releasing to CAD + PLM…")
        approve_release(runid)
        s = poll_until(runid, ("released",), on_progress=prog)
        did = s.get("design_id")
        if not did:
            return {"answer": f"⚠️ Release did not return a design id (phase {s.get('phase')}).", "pending": None, "intent": "cad_design"}
        prog(f"🗄 CAD + PLM released ({did}) — building the SAP genesis preview…")
        # sync the design S3->local so the D2M genesis adapter can read it, then PREVIEW (no SAP writes)
        try:
            _sync_design_local(did)
        except Exception as e:
            prog(f"(sync note: {e})")
        from cad_bridge import cad_genesis
        prev = cad_genesis(did, confirm=False, plant=plant)
        c = (prev.get("plan_data") or {}).get("counts", {})
        chain.append({"agent": "maker", "kind": "reasoning", "text": f"Released {did}; genesis preview ready."})
        body = (f"<div style='font-family:Arial'>Will create <b>{c.get('materials')}</b> materials · "
                f"{c.get('made')} made / {c.get('bought')} bought · {c.get('boms')} BOM · {c.get('routings')} routing · "
                f"{c.get('prod_versions')} PV · {c.get('pirs')} PIR.<div style='color:#666;margin-top:6px'>"
                f"Nothing written to SAP yet — this is the preview.</div></div>")
        cards.append({"tool": "genesis_preview", "result": _card(f"SAP genesis preview — {did}",
                                                                 f"{c.get('materials')} materials · no writes", body)})
        return {"answer": (f"🗄 **CAD + PLM created** ({did}). SAP **genesis preview** ready — "
                           f"{c.get('materials')} materials, {c.get('pirs')} PIR, {c.get('boms')} BOM. "
                           "**Approve** to write it to SAP."),
                "pending": {"stage": "awaiting_genesis", "runid": runid, "design_id": did},
                "cards": cards, "chain": chain, "intent": "cad_design"}

    # ---------- genesis gate -> COMMIT to SAP ----------
    if stage == "awaiting_genesis":
        did = pending.get("design_id")
        if not _is_affirm(text):
            return {"answer": f"Type **approve** to write {did} to SAP, or say stop.", "pending": pending, "intent": "cad_design"}
        prog(f"🏗 approved — committing {did} to SAP (materials · BOM · routing · PV · PIR)…")
        from cad_bridge import cad_genesis
        res = cad_genesis(did, confirm=True, plant=plant, on_step=(lambda ev: prog(ev.get("text", "")) if isinstance(ev, dict) and ev.get("kind") == "reasoning" else None))
        rec = res.get("reconciliation") or {}
        fg = res.get("fg_material")
        complete = bool(res.get("complete"))
        thread = res.get("cad_to_sap") or {}
        trows = "".join(f"<tr><td style='padding:2px 8px;font-family:monospace'>{k}</td><td style='color:#888'>→</td>"
                        f"<td style='padding:2px 8px;font-family:monospace;font-weight:bold'>{v}</td></tr>" for k, v in list(thread.items())[:30])
        rbody = (f"<div style='font-family:Arial'><div style='font-size:15px;font-weight:bold;color:{'#2e7d32' if complete else '#b5722a'}'>"
                 f"{'COMPLETE' if complete else 'INCOMPLETE'} — {rec.get('created')}/{rec.get('planned')} created · {len(rec.get('missing') or [])} missing</div>"
                 f"<div style='color:#666;margin-top:6px'>Independent re-read of SAP vs the CAD-intended spec.</div>"
                 f"<table style='margin-top:8px;border-collapse:collapse;font-size:12px'>{trows}</table></div>")
        cards.append({"tool": "reconciliation", "result": _card(f"SAP genesis — {did}",
                                                                f"FG {fg} · {rec.get('created')}/{rec.get('planned')}", rbody)})
        chain.append({"agent": "verifier", "kind": "reasoning",
                      "text": f"Reconciled {rec.get('created')}/{rec.get('planned')} — {'COMPLETE' if complete else 'INCOMPLETE'}."})
        ans = (f"🏗 **SAP genesis {'complete' if complete else 'INCOMPLETE'}** — FG **{fg}** · "
               f"reconciled **{rec.get('created')}/{rec.get('planned')}** · {len(thread)} CAD↔SAP mappings.")
        if complete:
            ans += "\n\nThe finished good is MRP-ready. **Approve** to create demand and run MRP, or you're done."
            return {"answer": ans, "pending": {"stage": "awaiting_plan", "runid": runid, "design_id": did, "fg": fg},
                    "cards": cards, "chain": chain, "intent": "cad_design"}
        ans += "\n\nSome objects did not create — see the reconciliation card. Re-run when ready."
        return {"answer": ans, "pending": None, "cards": cards, "chain": chain, "intent": "cad_design"}

    # ---------- plan gate -> demand + MRP ----------
    if stage == "awaiting_plan":
        fg = pending.get("fg")
        low = (text or "").lower()
        # explicit exit keeps the flow clean; ambiguous input KEEPS the gate (never drops to a generic agent).
        if re.search(r"\b(no|nope|stop|skip|done|finish|that'?s all|nothing)\b", low) and not _is_affirm(text):
            return {"answer": "👍 Done — the chain is complete.", "pending": None, "intent": "cad_design"}
        # trigger on an affirmation OR a natural demand/MRP instruction ("create a demand of 10 units …").
        is_plan = _is_affirm(text) or re.search(r"\b(demand|mrp|plan|forecast|pir|\d+\s*(units?|ea|pcs?))\b", low)
        if not is_plan:
            return {"answer": ("The finished good is **MRP-ready**. **Approve** to create demand + run MRP "
                               "(or say e.g. *'demand 100/month Aug–Dec'*), or say **done**."),
                    "pending": pending, "intent": "cad_design"}
        qty, period, period_to, span = _parse_demand(low)
        prog(f"📈 demand {qty} EA{(' · ' + span) if span else ''} + MRP for FG {fg}…")
        try:
            from planning_client import create_demand, run_mrp, read_mrp_list
            create_demand(material=fg, plant=plant, quantity=qty, period=period, period_to=period_to, confirm=True)
            mrp = run_mrp(material=fg, plant=plant, confirm=True)
            md04 = read_mrp_list(material=fg, plant=plant)
            po = re.search(r"Planned order\s+(\d+)", str(md04))
            n_per = 1 if not period_to else (int(period_to[4:]) - int(period[4:]) + 1 + 12 * (int(period_to[:4]) - int(period[:4])))
            body = (f"<div style='font-family:Arial'><div><b>Demand</b> — {n_per} PIR{'s' if n_per != 1 else ''} · "
                    f"{qty} EA{('/mo · ' + span) if period_to else (' · ' + span if span else '')}</div>"
                    f"<div style='margin-top:6px'><b>MRP</b> — multi-level</div>"
                    f"<div style='margin-top:6px'><b>MD04</b> — {'planned order <b>' + po.group(1) + '</b>' if po else 'elements produced'}</div></div>")
            cards.append({"tool": "mrp", "result": _card(f"Plan — demand + MRP · FG {fg}",
                                                         (f"planned order {po.group(1)}" if po else "MD04"), body)})
            chain.append({"agent": "planner", "kind": "reasoning", "text": f"Demand {qty} EA created, MRP run, MD04 read."})
            ans = (f"📈 **Demand + MRP done** for FG {fg} — {n_per} PIR{'s' if n_per != 1 else ''} of {qty} EA"
                   + (f", planned order **{po.group(1)}**" if po else "") + ". The full chain is complete. 🎉")
            return {"answer": ans, "pending": None, "cards": cards, "chain": chain, "intent": "cad_design"}
        except Exception as e:
            # keep the gate on error so the user can retry, not fall through to a generic agent
            return {"answer": f"⚠️ Demand/MRP error: {type(e).__name__}: {e}. Say **approve** to retry.",
                    "pending": pending, "intent": "cad_design"}

    return {"answer": "(cad flow: unexpected state)", "pending": None, "intent": "cad_design"}


def _sync_design_local(design_id: str):
    """Ask the AgentCAD backend to mirror a released design's JSON (ebom + part_masters) into the shared
    LOCAL cadplm_store, so the D2M genesis adapter (a local reader) can see an S3-mode design."""
    _post(f"/api/design/{design_id}/sync-local", timeout=60)
