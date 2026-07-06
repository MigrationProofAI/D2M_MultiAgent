"""web.py -- reuse the PARENT D2M React UI on the clean-room rig, via a THIN FastAPI bridge (NO ADK).
It serves the existing static_v2 build and speaks D2M's WebSocket protocol to our hand-rolled loop, so
the familiar chat + agent-activity panels work unchanged.

Honest scope: the rig has no genesis/boardroom/router/cards, so the Structured-Data / Tour / Demo
panels are sparse. The three capabilities surface where they belong:
  * chat answer + agent-activity trace (tool calls);
  * the "Learning" line carries the lessons-injected marker AND the memory + skills meters;
  * reading a material renders a Material card in the Data panel.

    uv run python web.py     ->     http://localhost:8000
"""
import os
import re
import json
import base64
import asyncio
import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from session import Session, SESSIONS_DIR
from session_title import ensure_title, cached_title
import session_meta
import anchors as session_anchors                     # typed SESSION ANCHORS: FG / plant / manifest / ledger
import s3_store
from memory import TieredMemory, ntok
from skills import SkillRegistry
from tools import set_skill_registry, set_current_session, TOOLS

# AUTHORITY SCOPING (Design -> Make -> PLAN). Planning tools belong to the PLANNER, not the Maker:
# the Maker BUILDS master data and its job ends at "born MRP-ready"; the Planner RUNS the plan. So the
# Maker (genesis + assist) and the Heal are scoped to master-data only -- they structurally cannot plan.
_PLANNING_TOOLS = {"create_demand", "read_demand", "run_mrp", "read_mrp_list", "read_mrp_material"}
MAKER_TOOLS = [n for n in TOOLS if n not in _PLANNING_TOOLS]                       # master-data only
# In THIS rig create_demand IS a Planned Independent Requirement (make-to-stock forecast via
# API_PLND_INDEP_RQMT_SRV) -- NOT a sales order. (agent-ui's create_demand is a legacy sales-order tool;
# there the Planner is scoped to create_plndindepreqmt instead.)
PLANNER_TOOLS = ["create_demand", "read_demand", "run_mrp", "read_mrp_list", "read_mrp_material",
                 "get_material", "get_bom", "read_production_version", "list_allowed_values",
                 "get_valid_mrp_controllers"]                                      # planning + read context
# The heal doer gets EVERY tool EXCEPT search_materials (so a fresh build cannot hunt+reuse an existing
# component -- the bicycle-parts-in-a-skateboard bug) AND except planning (that's the Planner's job).
_HEAL_TOOLS = [n for n in TOOLS if n != "search_materials" and n not in _PLANNING_TOOLS]
from agent import run_turn
from genesis_mode import GENESIS_PERSONA, is_genesis
from model_client import GENESIS_MODEL
from orchestrate import ORCHESTRATE_ON, verify_claim, verify_claim_chunked, subagent
from object_verifier import verify_genesis_objects   # deterministic genesis gate: ~0 tokens, no context limit
import verification_cards                             # render verifier output as Structured-Data cards (in Python)
from boardroom import convene_board, _verdict_of
from guide import is_platform_question, is_completion_question, GUIDE_PERSONA
from planner import PLANNER_PERSONA, is_planning
import cad_design                                       # UNIFIED flow: D2M drives AgentCAD (design/2D/3D) as a backend
import tts

# Convene the cross-functional board on a genesis PREVIEW (before the human confirms). On by default when
# the multi-agent loop is on; set RIG_BOARD=off to skip it.
BOARD_ON = os.getenv("RIG_BOARD", "on").lower() in ("1", "on", "true", "yes")
import learn

# Tools whose confirm=true commits a real write to SAP/planning. A genesis turn that includes one of
# these is "doer claims it created something" -> the verify loop should certify it (when the flag is on).
_WRITE_TOOLS = {"run_genesis", "load_bom_from_file", "enable_plant_production", "create_material",
                "update_material", "create_bom", "add_bom_component", "remove_bom_component",
                "extend_to_plant", "create_demand", "run_mrp", "create_info_record",
                "create_cost_condition", "change_material", "change_routing", "change_pir",
                "change_cost_condition", "change_bom", "set_routing_operation", "set_supplier_terms",
                "set_condition_price"}


def _committed_write(steps) -> bool:
    """True if this turn actually committed a write (a write tool called with confirm=true)."""
    for s in steps or []:
        if s.get("kind") == "tool_call" and s.get("tool") in _WRITE_TOOLS:
            if (s.get("args") or {}).get("confirm") is True:
                return True
    return False


_AFFIRM = re.compile(r"^\s*(go\s*ahead|go|yes|yep|yeah|ok(ay)?|sure|proceed|confirm|commit|do\s*it|"
                     r"create\s*(them|it)?|build\s*it|make\s*(them|it)?|approved?|ship\s*it)\b[\s.!`]*$", re.I)


def _is_affirmation(text) -> bool:
    """A short, unambiguous 'yes, go' — used to route a pending BOM-file COMMIT deterministically instead of
    letting the model re-interpret the plan. Kept strict (whole-message match) so a real instruction that just
    happens to start with 'go' (e.g. 'go create a demand') does NOT count."""
    return bool(_AFFIRM.match((text or "").strip()))


def _bom_preview_call(steps):
    """(path, enrich) of a load_bom_from_file PREVIEW (confirm not true) in these steps, else None. This is
    what a genesis file PREVIEW looks like; remembering it lets the next 'go ahead' commit the SAME parsed
    (deep) spec deterministically -- never a model-rebuilt run_genesis spec that flattens the hierarchy."""
    for s in steps or []:
        if s.get("kind") == "tool_call" and s.get("tool") == "load_bom_from_file":
            a = s.get("args") or {}
            if a.get("confirm") is not True and a.get("path"):
                return str(a.get("path")), bool(a.get("enrich"))
    return None


def _committed_bom_path(steps):
    """Path of a load_bom_from_file COMMIT (confirm=True) in these steps, else None -- lets the verify loop
    re-parse the spec and run the CONFORMANCE audit (actual SAP vs intended contract) on a file-driven genesis."""
    for s in steps or []:
        if s.get("kind") == "tool_call" and s.get("tool") == "load_bom_from_file":
            a = s.get("args") or {}
            if a.get("confirm") is True and a.get("path"):
                return str(a.get("path"))
    return None


def _planned_material(steps):
    """(material, plant) of a CONFIRMED run_mrp this turn, else None. An MRP run creates no materials to
    anchor a master-data verifier on -- so we anchor the recursive MRP-TREE validator on what was planned."""
    for s in steps or []:
        if s.get("kind") == "tool_call" and s.get("tool") == "run_mrp":
            a = s.get("args") or {}
            if a.get("confirm") is True and a.get("material"):
                return str(a.get("material")), str(a.get("plant", "1710"))
    return None


# D2M material numbers are 5-digit 1xxxx (e.g. 11757). BOM (00000508), routing (50000322), PIR
# (5300007194) and cost-condition numbers are 8-10 digits, so this pattern picks materials only.
_MATNUM = re.compile(r"\b(1\d{4})\b")
_CREATE_TOOLS = {"create_material", "run_genesis", "load_bom_from_file", "enable_plant_production",
                 "create_bom", "build_material_payload"}
_NON_MATERIAL_NUMS = {"10000", "100000"}   # production-version lot-size bounds, not materials

# A material number is only anchored when it appears in an EXPLICIT material context inside a creation
# result -- "material 12055", "Product":"12055", "FERT 12059", or "12059 (HALB)". A bare 1xxxx (a change
# doc, an internal id like the stray 12829) is NOT a created material and must never enter the scope.
_MAT_CREATE = re.compile(
    r"(?:material|product|created|FERT|HALB|HAWA|ROH)\W{0,5}(1\d{4})"   # keyword BEFORE the number
    r"|(1\d{4})\s*\(?\s*(?:FERT|HALB|HAWA|ROH)",                        # type code AFTER the number
    re.I)


def _created_materials(steps) -> list:
    """The AUTHORITATIVE scope: material numbers actually CREATED this turn. Mines ONLY the results of
    material-creating tools (not web search, not reads), and ONLY numbers in an explicit material context
    (see _MAT_CREATE) -- so a stray id like '12829' that merely appeared in a result can't poison the
    scope. Also drops numbers seen in a google_search result and the PV lot-size 10000. This anchors the
    verifier to THIS genesis's real materials and stops the heal loop chasing a phantom."""
    web_nums, create_nums = set(), set()
    for s in steps or []:
        if s.get("kind") != "tool_result":
            continue
        res = str(s.get("result", ""))
        tool = s.get("tool")
        if tool == "google_search":
            web_nums.update(_MATNUM.findall(res))
        elif tool in _CREATE_TOOLS:
            for a, b in _MAT_CREATE.findall(res):
                if a:
                    create_nums.add(a)
                if b:
                    create_nums.add(b)
    return sorted(create_nums - web_nums - _NON_MATERIAL_NUMS)


_GAP_OBJ = re.compile(r"(routing|production[- ]?version|prod\.? ?ver|BOM|PIR|price|CountryOfOrigin|plant[- ]?view|material)", re.I)


def _gap_summary(verdict, limit=4):
    """A short human-readable list of WHAT is missing (e.g. '11758 routing, 13449 material (404)') pulled
    from the verifier's verdict, so the status line names the gap instead of just counting it."""
    out, seen = [], set()
    for ln in (verdict or "").splitlines():
        if "MISSING" not in ln.upper():
            continue
        mats = _MATNUM.findall(ln)
        obj = _GAP_OBJ.search(ln)
        label = (mats[0] if mats else "?")
        if obj:
            label += " " + obj.group(1).lower()
        if "404" in ln:
            label += " (404)"
        if label not in seen:
            seen.add(label)
            out.append(label)
    txt = ", ".join(out[:limit])
    return (txt + "…") if len(out) > limit else txt


# Auto-heal cap (the loop-breaker with teeth). The user already authorised the genesis ("go ahead"),
# so finishing THAT job is in scope; the cap bounds it.
HEAL_MAX = int(os.getenv("RIG_HEAL_MAX", "5"))


def _heal_prompt(verdict: str, steer_notes=None) -> str:
    """Hand the verifier's classified gap list back to the SAME genesis doer to CLOSE the MISSING gaps."""
    steer = ""
    if steer_notes:
        steer = ("\n\n--- USER STEERING (apply this guidance; it overrides the gap list where they "
                 "conflict) ---\n" + "\n".join(f"- {n}" for n in steer_notes) + "\n")
    return (
        "An independent, read-only verifier checked your genesis against SAP and it is NOT complete. "
        "It read SAP back and classified each object. Here is its report:\n\n" + (verdict or "") + steer + "\n\n"
        "CREATE the objects it marked MISSING now (the user already authorised this genesis with 'go "
        "ahead', so commit with confirm=true).\n"
        "🚫 FRESH BUILD — DO NOT REUSE OLD MATERIALS. This genesis creates everything new. **NEVER call "
        "search_materials**, and **NEVER put an existing/pre-existing material number into a BOM**. The "
        "components you need are the ones in THIS assembly's plan (from the image/spec earlier in this "
        "conversation) — e.g. a skateboard wheel's parts are a skateboard tire/rim/bearing, NOT a "
        "bicycle's spokes. If you find yourself searching SAP for a component or adding an 11xxx number "
        "from a previous build, STOP — that is the bug.\n"
        "For a missing HALB sub-assembly BOM: for EACH of its components, call create_material to make a "
        "BRAND-NEW material (use the component's name/type from this assembly's plan), plant-extend it, "
        "THEN create_bom using those NEW component numbers (the ones you just created in this turn). For a "
        "missing PIR/price on a bought (HAWA) component: create_info_record(material, supplier, "
        "net_price=...) THEN create_cost_condition(material, supplier, price=...) — only for THIS build's "
        "new materials, with the component's vendor (default 17300001) and its price. For a missing "
        "ROUTING or PRODUCTION VERSION on a made material (a HALB sub-assembly), call "
        "enable_plant_production(material=<the HALB>, plant=<plant>). For a missing PLANT VIEW "
        "(a material born basic-view-only), call extend_to_plant(material, plant, product_type=<its type>, "
        "mrp_type='PD', confirm=true) — every created material must carry its plant view. "
        "PRICE GAP on an EXISTING info record (NetPriceAmount reads ~0.01, and it is NOT marked MISSING): do "
        "NOT re-create it — a second POST of an info record that already exists FAILS ('Address texts do not "
        "exist'). Correct the purchasing condition via set_condition_price / change_cost_condition WITH the "
        "currency; the info-record net price is create-only, so if it cannot be patched, report it — do NOT "
        "loop on create. "
        "Ignore anything marked UNVERIFIED. Fix ONLY the MISSING items for THIS assembly; do not recreate "
        "what you already made this session, and do not reuse anything from a past session. Then report.")


HERE = Path(__file__).parent
STATIC = HERE / "static_v2"
BASE_SYSTEM = ("You are a SAP master-data assistant in a clean-room rig. Use your tools and skills. "
               "When a task matches a skill, call load_skill(name) first. Apply any injected LESSONS. "
               "Format answers in Markdown -- headings, **bold**, lists, and tables all render.")
CHAT_MAX_STEPS = int(os.getenv("RIG_MAX_STEPS", "16"))   # tool-call budget per CHAT turn (genesis path uses 20)

app = FastAPI()
_REG = SkillRegistry()
set_skill_registry(_REG)
_SESSIONS = {}                                       # sid -> {mem, prev_intent, last_answer}


@app.on_event("startup")
def _s3_hydrate_on_boot():
    """On boot, pull persisted sessions + lessons/skills from S3 so a CF push doesn't wipe history.
    No-op unless S3_PERSIST is on. faiss rebuilds from the hydrated lessons.jsonl on first use."""
    try:
        if s3_store.ENABLED:
            print(f"[s3_store] hydrating from s3://{os.getenv('S3_BUCKET')}/{os.getenv('S3_PREFIX','d2m')}/ …", flush=True)
            print(f"[s3_store] hydrated {s3_store.hydrate()}", flush=True)
        else:
            print("[s3_store] S3_PERSIST off — local-only (no hydrate)", flush=True)
    except Exception as e:
        print(f"[s3_store] hydrate skipped: {e}", flush=True)


def _classify(text):
    t = (text or "").lower()
    return ("create_change" if any(w in t for w in
            ("create", "material", "bom", "component", "plant", "extend", "routing", "pir")) else "assist")


def _state(sid):
    st = _SESSIONS.get(sid)
    if st is None:
        sess = Session(sid)
        mem = TieredMemory(sess, system=BASE_SYSTEM,
                           budget=int(os.getenv("RIG_BUDGET", "4000")), min_working=6)
        # REHYDRATE the working set from disk so a reopened session is actually remembered (not just
        # re-displayed). The image bytes stay on disk; only a marker rides in context.
        for t in sess.reload_turns():
            if t["role"] == "user":
                mem.working.append({"role": "user",
                                    "content": (t["text"] or "") + (" [image attached]" if t.get("image") else "")})
            elif t["role"] == "assistant" and t.get("text"):
                mem.working.append({"role": "assistant", "content": t["text"]})
        mem.maybe_compact()                          # if the reloaded history is large, compact it now
        st = {"mem": mem, "prev_intent": "assist", "last_answer": ""}
        _SESSIONS[sid] = st
    return st


def _cards(steps):
    """Forward structured cards to the React Data panel. Previously this only emitted get_material +
    run_genesis cards, so every OTHER tool's structured output (enable_plant_production, create_bom,
    create_routing, get_bom, PIR/cost, demand/MRP, ...) was dropped and only ever reached the chat. Now
    ANY tool result carrying an @@DATA@@ block forwards its typed card (tagged by tool); get_material
    still renders its Material card. (How each card KIND renders is up to the React bundle.)"""
    out = []
    for s in steps:
        if s.get("kind") != "tool_result":
            continue
        tool = s.get("tool")
        result = s.get("result") or ""
        if "@@DATA@@" in result:                       # any tool that emits a typed card
            try:
                out.append({"tool": tool, "payload": json.loads(result.split("@@DATA@@", 1)[1])})
                continue
            except Exception:
                pass
        if tool == "get_material":                     # material read -> Material card (no @@DATA@@)
            try:
                d = json.loads(result)
                if isinstance(d, dict) and d.get("d"):
                    out.append({"tool": "get_material", "payload": {"d": d["d"]}})
            except Exception:
                pass
    return out


# ---- root serves the UNIFIED Studio (the warm-paper 3-pane app) ----
@app.get("/")
def index():
    # :9100 IS the Studio now — the merged Ideate->Design->Make->Plan app. The old React bundle is at /legacy.
    return FileResponse(HERE / "studio.html", headers={"Cache-Control": "no-cache, must-revalidate"})


@app.get("/legacy")
def legacy():
    # the previous built React UI, kept reachable. never cache its index (hashed-bundle rebuilds).
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache, must-revalidate"})


@app.get("/intro")
def intro():
    # The "meet the operator" explainer: a self-contained, first-person animated walkthrough (nova voice
    # + a diagram that builds as it narrates). Lives beside web.py (stable -- NOT in static_v2, which the
    # frontend build wipes). Same-origin, so it reuses /api/tts for the cached nova narration.
    return FileResponse(HERE / "intro.html", headers={"Cache-Control": "no-cache, must-revalidate"})


@app.get("/studio")
def studio():
    # The UNIFIED Studio: the warm-paper 3-pane UI (Conversation | Agent Activity | Part Lineage), the
    # locked design language for the merged Ideate->Design->Make->Plan app. Self-contained, lives beside
    # web.py (stable, NOT in static_v2). Speaks the same WS + session REST as the React app.
    return FileResponse(HERE / "studio.html", headers={"Cache-Control": "no-cache, must-revalidate"})


@app.get("/cadviewer/{slug}")
def cadviewer(slug):
    """SAME-ORIGIN proxy of AgentCAD's self-contained interactive 3D viewer (viewer.html — rotate/explode/
    home, geometry built inline from assembly_spec.json + three.js from CDN). Proxying the HTML means the
    Studio can frame it same-origin (:9100), so the 3D renders reliably with no cross-origin framing doubt."""
    import urllib.request
    base = os.getenv("AGENTCAD_URL", "http://127.0.0.1:5005").rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/viewer/{slug}/", timeout=15) as r:
            html = r.read().decode("utf-8", "replace")
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})
    except Exception as e:
        return HTMLResponse(f"<body style='font-family:monospace;padding:20px;color:#8A8578'>3D viewer "
                            f"unavailable for {slug}: {e}</body>", status_code=502)


app.mount("/assets", StaticFiles(directory=str(STATIC / "assets")), name="assets")


# ---- stub the /api endpoints the React app pings on load (so panels don't error) ----
@app.get("/api/sessions")
def _sessions():
    """List persisted rig sessions (newest first) for the Sessions browser.

    The dropdown renders `title`, so we compose a DATETIME-STAMPED, intuitive label there
    ("Jun 29, 22:08 · Please run the genesis · 12 turns") instead of a bare first-message that reads
    the same for every drone run. Also emit structured created/modified/gist for a future richer UI
    and for the S3 session keys (Phase 1)."""
    out = []
    if SESSIONS_DIR.exists():
        # exclude internal sub-agent sessions (maker/board/chair/verifier are minted "orch-…" in
        # orchestrate.subagent) -- they are not user conversations and made the dropdown unusable.
        dirs = [d for d in SESSIONS_DIR.iterdir()
                if d.is_dir() and (d / "trace.jsonl").exists() and not d.name.startswith("orch-")]
        # WALL CLOCK: time the session by meta.json (the REAL time stamped at each turn) -- immune to
        # file mtimes, which the S3 hydrate rewrites to boot time on every CF push. Fall back to
        # trace.jsonl mtime only for old sessions that predate meta.json.
        def _eff(d):
            c_iso, u_iso = session_meta.times(d)
            if u_iso:
                mdt = datetime.datetime.fromisoformat(u_iso)
                return (c_iso or u_iso), u_iso, mdt
            st = (d / "trace.jsonl").stat()
            mdt = datetime.datetime.fromtimestamp(st.st_mtime)
            return (datetime.datetime.fromtimestamp(st.st_ctime).isoformat(timespec="seconds"),
                    mdt.isoformat(timespec="seconds"), mdt)
        rows = sorted(((_eff(d), d) for d in dirs), key=lambda r: r[0][2], reverse=True)
        for (c_iso, m_iso, mdt), d in rows:
            turns = Session(d.name).reload_turns()
            n = sum(1 for t in turns if t["role"] == "user")
            gist = next((t["text"].strip() for t in turns if t["role"] == "user" and t.get("text")), "")
            gist = (gist[:48] + "…") if len(gist) > 48 else (gist or "(empty session)")
            ai = cached_title(d)                              # AI title if generated (NO spend in the list path)
            display = ai or gist
            label = f"{mdt:%b %d, %H:%M} · {display} · {n} turn{'' if n == 1 else 's'}"
            out.append({"id": d.name, "title": label, "ai_title": ai, "gist": gist, "turns": n,
                        "created": c_iso, "modified": m_iso})
    return out


@app.get("/api/sessions/{sid}/events")
def _events(sid):
    """Reload a session's chat from disk -> the UI re-renders it on restart / switch. An attached
    image is returned as a SERVABLE URL (not a bare boolean) so the UI shows the real picture on
    reload, not just a '[image attached]' marker. Bytes still live on disk; only the URL rides here."""
    out = []
    for t in Session(sid).reload_turns():
        img = t.get("image")
        url = None
        if img and img.get("on_disk"):
            name = img["ref"].replace("\\", "/").split("/")[-1]   # "assets/<hash>.<ext>" -> "<hash>.<ext>"
            url = f"/api/sessions/{sid}/asset/{name}"
        out.append({"role": t["role"], "text": t["text"], "image": url})
    return out


@app.get("/api/sessions/{sid}/asset/{name}")
def _session_asset(sid, name):
    """Serve a blob evicted to a session's assets/ folder (the disk side of tiered memory). Basename
    only -- no path traversal out of the session dir."""
    name = name.replace("\\", "/").split("/")[-1]
    p = Session(sid).asset_path("assets/" + name)
    if not p.exists() or not p.is_file():
        return JSONResponse({"error": "asset not found"}, status_code=404)
    return FileResponse(str(p))


@app.get("/api/sessions/{sid}/trace")
def _trace(sid):
    """Per-turn activity (intent + tool steps) so the Agent-Activity + Structured-Data panels are
    rebuilt on reload. Returns [] for old sessions that pre-date activity persistence."""
    p = Session(sid).dir / "activity.jsonl"
    out = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


@app.get("/api/kg")
def _kg():
    return {"nodes": [], "edges": []}


@app.post("/api/cad/genesis")
async def _cad_genesis(payload: dict = None):
    """CAD → D2M handoff (Phase 6): AgentCAD posts a RELEASED design_id; D2M builds the genesis spec and
    either previews it (confirm=false — the board's decision card, no SAP writes) or commits it
    (confirm=true — materials + BOM + routing + PV + PIR/cost, anchored + reconciled + conformance-checked
    vs the CAD-intended spec), returning the CAD-part# ↔ SAP-material# digital thread. This IS the POST
    that AgentCAD's emit_to_plm_erp stub deferred."""
    payload = payload or {}
    design_id = payload.get("design_id")
    if not design_id:
        return JSONResponse({"error": "design_id is required"}, status_code=400)
    try:
        from cad_bridge import cad_genesis
        res = await asyncio.to_thread(cad_genesis, design_id, bool(payload.get("confirm")),
                                      payload.get("plant"), payload.get("store_root"))
        return JSONResponse(res)
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=500)


@app.post("/api/explain")
async def _explain(payload: dict = None):
    return {"text": "(rig) explanations aren't wired -- this is the clean-room test rig."}


@app.post("/api/explain_app")
async def _explain_app(payload: dict = None):
    """The spoken product tour's script. Each section's `id` drives which pane/element the UI highlights
    (see paneFor/spotFor in App.jsx); `text` is narrated. Curated (reliable for demos) and on-message
    about the multi-agent architecture."""
    return {"sections": [
        {"id": "intro", "label": "Design2Make",
         "text": "Welcome to Design2Make. It turns a picture of a product into a complete, validated set "
                 "of SAP master data — and under the hood it isn't one assistant, it's a team of bounded "
                 "AI agents working together."},
        {"id": "multimodal", "label": "Multimodal input",
         "text": "You work here in plain language. Paste a Bill-of-Materials image, describe an assembly, "
                 "or just ask — the system reads the picture and your words together to understand the "
                 "product hierarchy."},
        {"id": "genesis", "label": "Maker and Verifier",
         "text": "When you confirm, a Maker agent creates the materials, BOMs, routings and prices. Then a "
                 "separate, read-only Verifier independently re-reads SAP and certifies the result. The "
                 "agent that builds is never the agent that signs off — that's the core safeguard."},
        {"id": "board", "label": "The boardroom",
         "text": "Before you commit, a cross-functional board convenes on the plan. Engineering, "
                 "Procurement, Compliance, Finance and Planning each give a go or no-go from their own "
                 "lens, and a Chair synthesizes them into one decision."},
        {"id": "panels", "label": "Watch it think",
         "text": "Everything is transparent. The Agent Activity panel streams each agent's reasoning and "
                 "actions, tagged by who is acting, while the Structured Data panel renders the live SAP "
                 "objects as cards."},
        {"id": "discipline", "label": "Self-healing",
         "text": "If the Verifier finds a gap, a capped heal loop hands it back to the Doer to fix and "
                 "then re-checks — so the system either finishes the job or tells you honestly what is "
                 "still missing. It never claims done when it isn't."},
        {"id": "cta", "label": "Try it",
         "text": "Drop a Bill-of-Materials image and say: run its genesis. Then watch the agents "
                 "deliberate, build, and certify your assembly end to end."},
    ]}


@app.post("/api/tts")
async def _tts(payload: dict = None):
    """One short TTS clip (the tour + the voiced Guide). Returns {audio_b64} -- "" when RIG_TTS is off,
    no key, or it fails, and the client falls back to captions. Cached so the fixed tour is ~free."""
    text = ((payload or {}).get("text") or "").strip()
    voice = (payload or {}).get("voice")
    b64 = await asyncio.to_thread(tts.synth, text, voice)
    return {"audio_b64": b64}


# ---- the chat: D2M's WS protocol, our hand-rolled loop behind it ----
@app.websocket("/ws/{sid}")
async def ws(websocket: WebSocket, sid: str):
    await websocket.accept()
    st = _state(sid)
    deferred = []                                  # normal messages received mid-run -> process next

    async def _drain_steer():
        """Non-blocking: pull any messages the user sent WHILE a turn is running. A '/btw <note>' (or a
        {steer:...} message) becomes live steering for the next heal pass; '/btw stop' halts the loop; any
        other message is deferred to run as its own turn afterwards. Returns (notes, stop)."""
        notes, stop = [], False
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=0.02)
            except Exception:
                break
            try:
                e = json.loads(raw)
            except Exception:
                e = {"text": raw}
            s = e.get("steer")
            t = (e.get("text") or "").strip()
            if s is None and t.lower().startswith("/btw"):
                s = t[4:].strip()
            if s is None:
                deferred.append(raw)               # a real next-turn message; handle after this turn
            elif s.lower() in ("stop", "halt", "cancel"):
                stop = True
            elif s:
                notes.append(s)
        return notes, stop

    while True:
        if deferred:
            raw = deferred.pop(0)
        else:
            try:
                raw = await websocket.receive_text()
            except Exception:
                break
        try:
            env = json.loads(raw)
        except Exception:
            env = {"text": raw}
        text = (env.get("text") or "").strip()
        img = None
        data = (env.get("image") or {}).get("data")
        if data:
            if "," in data and data.strip().startswith("data:"):
                data = data.split(",", 1)[1]
            try:
                img = base64.b64decode(data)
            except Exception:
                img = None
        if env.get("steer") is not None:
            # a /btw arrived at the main loop -> no task is running (a live loop consumes steers itself).
            # Tell the user instead of silently dropping it, so /btw never just vanishes.
            await websocket.send_text(json.dumps({"type": "note", "text":
                "↪ Nothing to steer right now — no task is running. /btw steers a genesis/heal loop "
                "while it's in progress. To act now, send a normal message (e.g. \"retry\")."}))
            continue
        if not text and not img:
            continue

        await websocket.send_text(json.dumps({"type": "status", "text": "working…"}))
        mem = st["mem"]
        set_current_session(mem.session)              # so write_skill_artifact / promote_skill know the session

        # EXCEL BOM UPLOAD: an attached .xlsx arrives on the image channel but starts with the ZIP
        # signature (PK\x03\x04) -- a vision image never does. So it's a DETERMINISTIC genesis input:
        # save it and rewrite the turn as the load_bom_from_file chat flow, which reuses the existing
        # preview + board + confirm. No vision model, lossless.
        if img and img[:4] == b"PK\x03\x04":
            _bomdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
            os.makedirs(_bomdir, exist_ok=True)
            _bompath = os.path.join(_bomdir, f"bom_{mem.session}.xlsx")
            with open(_bompath, "wb") as _f:
                _f.write(img)
            await websocket.send_text(json.dumps({"type": "note", "text":
                f"\U0001F4C4 Excel BOM received ({len(img) // 1024} KB) — parsing deterministically (no vision model)…"}))
            text = f"load bom from file {_bompath}"
            img = None

        # LIVE REASONING CHAIN: turn the opaque "working…" into a running, agent-labelled account of what
        # each agent is thinking and doing. Two channels: a transient `status` (the spinner line) and a
        # PERSISTENT `activity` event the Agent-Activity panel appends. on_step fires inside run_turn (in a
        # worker thread), so sends are scheduled back on this event loop.
        loop = asyncio.get_running_loop()
        async def _send(obj):
            try:
                await websocket.send_text(json.dumps(obj))
            except Exception:
                pass
        def _status(t):
            asyncio.run_coroutine_threadsafe(_send({"type": "status", "text": t}), loop)
        chain_log = []                                 # every activity event this turn, for persistence/replay
        def _activity(agent, kind, **fields):
            ev = {"agent": agent, "kind": kind, **fields}
            chain_log.append(ev)                       # save the THOUGHTS (list.append is thread-safe)
            asyncio.run_coroutine_threadsafe(_send({"type": "activity", **ev}), loop)
        _HINT_KEYS = ("material", "material_id", "component", "description", "query", "name", "supplier", "plant")
        def _emitter(agent):
            """A run_turn on_step callback tagged with WHICH agent is acting (doer / verifier)."""
            def _cb(ev):
                if ev.get("kind") == "reasoning":
                    txt = (ev.get("text") or "").strip()
                    _activity(agent, "reasoning", text=txt)
                    first = txt.replace("\n", " ")[:80]
                    _status(f"🧠 {agent}: {first}…")
                elif ev.get("kind") == "usage":        # TELEMETRY: this agent-turn's tokens + MCP calls
                    _activity(agent, "usage", tokens_in=ev.get("in", 0),
                              tokens_out=ev.get("out", 0), calls=ev.get("calls", 0), mcp=ev.get("mcp"))
                else:                                  # a tool call
                    a = ev.get("args") or {}
                    hint = next((str(a[k]) for k in _HINT_KEYS if a.get(k)), "")
                    if not hint:
                        hint = next((str(v) for v in a.values() if isinstance(v, (str, int, float))), "")
                    tool = ev.get("tool", "")
                    try:                                 # TELEMETRY: which cloud MCP server this tool hits
                        import mcp_route as _mr
                        _mcp = _mr.server_for(tool)
                    except Exception:
                        _mcp = None
                    _activity(agent, "tool", tool=tool, hint=hint[:48], mcp=_mcp)
                    _status(f"→ {agent}: {tool}" + (f" {hint[:36]}" if hint else "") + "…")
            return _cb
        def _conductor(text):                          # orchestration phase (verify / heal) -> both channels
            _activity("conductor", "phase", text=text)
            _status(text)
        _emit = _emitter("doer")                       # the doer narrates by default

        steps = []
        _pending = st.get("pending_bom")
        if _pending and not img and _is_affirmation(text) and os.path.exists(_pending.get("path", "")):
            # DETERMINISTIC FILE-BOM COMMIT: the user is confirming a BOM-file preview. Re-run the SAME
            # deterministic parse+build (load_bom_from_file), NOT the model's discretion -- the model
            # sometimes re-composes a run_genesis spec and FLATTENS the hierarchy (L4 built only 5 of 23,
            # session 38682bf9; also forced healing on 76182701). The parsed spec is the source of truth;
            # the commit must use it verbatim. Then the normal verify/heal loop runs on what was created.
            intent = "genesis"
            injected, lessons = False, []
            _p, _enr = _pending["path"], _pending.get("enrich", False)
            _conductor(f"🧱 committing the parsed BOM deterministically — {os.path.basename(_p)}"
                       + (" (+web-sourcing)" if _enr else "") + " — no model re-interpretation")
            _activity("doer", "tool", tool="load_bom_from_file", hint=os.path.basename(_p))
            from tools import load_bom_from_file as _lbff
            answer = await asyncio.to_thread(_lbff, _p, True, _enr, _emit)  # path, confirm, enrich, LIVE stream
            steps.append({"author": "doer", "kind": "tool_call", "tool": "load_bom_from_file",
                          "args": {"path": _p, "confirm": True, "enrich": _enr}})
            steps.append({"author": "doer", "kind": "tool_result", "tool": "load_bom_from_file",
                          "result": str(answer)[:8000]})
            st["pending_bom"] = None
            learn_line = "DETERMINISTIC file-BOM commit (bypassed model spec-rebuild — no flattening)"
        elif st.get("pending_cad") or cad_design.is_cad_design(text, img is not None):
            # UNIFIED Ideate→Design→Make→Plan: D2M is the ONE app; a "design a …" prompt (or an in-flight
            # design gate) is driven here by orchestrating AgentCAD (:5005) as a CAD backend, then D2M's
            # own genesis + planning. Each stage is a normal D2M turn (pending_cad carries the gate), so
            # the whole chain persists as ONE D2M session (chat + agent-activity + cards).
            intent = "cad_design"
            injected, lessons = False, []
            mem.add_user(text, img, "image/png" if img else None)   # persist the turn (no run_turn here)
            _pcad = st.get("pending_cad")
            _dtext = text
            if not _pcad:                                # NEW design: a vague reference ("what about the 2d
                # design?") has no product of its own -> design the subject we've been discussing, not the
                # literal question. Resolve from the recent user turns (newest first).
                _recent = [t.get("text", "") for t in mem.session.reload_turns() if t.get("role") == "user"]
                _dtext = cad_design.resolve_design_intent(text, list(reversed(_recent)))
            _conductor("🎛 design → make → plan (unified)…"
                       + (f"  ↪ designing “{_dtext[:52]}”" if _dtext != text else ""))

            def _cad_prog(msg):
                if msg:
                    _conductor(msg if len(str(msg)) < 90 else str(msg)[:88] + "…")
            res = await asyncio.to_thread(cad_design.drive_cad_stage, mem.session, _pcad, _dtext, "1710", _cad_prog)
            answer = res.get("answer", "")
            st["pending_cad"] = res.get("pending")
            _ref = res.get("image_ref")
            if _ref:                                     # show the 2D/3D inline (markdown) + as a durable chat image
                _name = _ref.split("/")[-1]
                answer += f"\n\n![design](/api/sessions/{sid}/asset/{_name})"
                mem.session.append_trace({"role": "assistant", "text": "[design image]", "image_ref": _ref})
            for _c in res.get("cards", []):              # Structured-Data cards
                steps.append({"author": "cad", "kind": "tool_result", "tool": _c["tool"], "result": _c["result"]})
            for _ev in res.get("chain", []):             # Agent-Activity events
                _activity(_ev.get("agent", "cad"), _ev.get("kind", "reasoning"),
                          **{k: v for k, v in _ev.items() if k not in ("agent", "kind")})
            mem.add_assistant({"content": answer})
            learn_line = "CAD-DESIGN unified flow · stage=" + str((res.get("pending") or {}).get("stage") or "complete")
        elif is_completion_question(text) and not img:
            # VERIFIED COMPLETION (B2): a completion/verification question NEVER gets an agent's answer.
            # The Guide narrates (no SAP tools -> it cannot verify), the doer is optimistic (it wrote the
            # claim being checked) -- so this is routed, at dispatch, to the Verifier's MANIFEST
            # RECONCILIATION: the declared manifest (typed session state) vs a live SAP re-read. The FIRST
            # answer is the reconciliation, not narration -- the user never has to ask twice. Checked
            # BEFORE the Guide/genesis/planning branches so their keywords can't hijack the question.
            intent = "verify"
            injected, lessons = False, []
            _anch = session_anchors.read(mem.session.dir)
            _aspec = session_anchors.spec_of(_anch)
            if _anch and _aspec:
                _conductor("🧾 completion question → manifest reconciliation (independent re-read, never narration)…")
                from conformance import reconcile_manifest as _rman
                _vplant = _anch.plant or "1710"
                _scope = list(_anch.created_ledger or [])
                if _anch.fg_material and _anch.fg_material not in _scope:
                    _scope.append(_anch.fg_material)
                _rrep, _rrec = await asyncio.to_thread(_rman, _aspec, _scope, _vplant, _emitter("verifier"))
                _rbanner = ("✅ COMPLETE — every planned object reconciles against SAP (zero missing)"
                            if _rrec.get("complete") else
                            f"⛔ INCOMPLETE — {len(_rrec.get('missing') or [])} of {_rrec.get('planned')} "
                            f"planned object(s) MISSING in SAP")
                answer = f"### 🧾 {_rbanner}\n{_rrep}"
                # per-object completeness (BOM/routing/PV/PIR/cost + plant view) on the same live scope
                if _scope:
                    _p2, _m2, _u2, _v2, _vd2 = await asyncio.to_thread(
                        verify_genesis_objects, _scope, _vplant, _emitter("verifier"))
                    answer += f"\n\n---\n### 🔍 Object detail (independent read-back)\n{_v2}"
                    try:
                        steps.append({"author": "verifier", "kind": "tool_result", "tool": "genesis_verification",
                                      "result": verification_cards.genesis_card(_vd2)})
                    except Exception:
                        pass
                steps.append({"author": "verifier", "kind": "tool_result", "tool": "reconciliation",
                              "result": _rrep + "\n@@DATA@@" + json.dumps(_rrec, ensure_ascii=False, default=str)})
                learn_line = ("VERIFIED-COMPLETION route: manifest reconciliation "
                              f"({_rrec.get('created')}/{_rrec.get('planned')} planned, "
                              f"{len(_rrec.get('missing') or [])} missing)")
            else:
                # honest no-anchor surface (mirrors the verify-skip guard): with no manifest in THIS
                # session there is nothing to certify against -- say so, never guess a verdict.
                answer = ("### 🧾 Nothing to reconcile against\nNo genesis has anchored a manifest in this "
                          "session, so there is no declared plan to verify completion against. Run (or "
                          "re-open the session of) the genesis you mean, or name the FERT material and I "
                          "can verify its live BOM tree object-by-object instead.")
                learn_line = "VERIFIED-COMPLETION route: no manifest anchored — honest no-verdict"
        elif is_platform_question(text) and not img:
            # THE GUIDE (the "demo lady"): a meta question ABOUT the tool/architecture, not a master-data
            # task -> a read-only Guide agent explains it, briefly and spoken-style. The client speaks the
            # answer in the nova voice. No SAP tools, no writes.
            intent = "guide"
            injected, lessons = False, []
            _status("🎙️ guide…")
            _activity("guide", "reasoning", text="Explaining the platform…")
            answer = await asyncio.to_thread(subagent, GUIDE_PERSONA, text, False, 4, "guide")
            learn_line = "GUIDE mode: read-only platform explainer (nova voice)"
        elif is_genesis(text, img is not None):
            # DESIGN2MAKE: genesis persona + the vision model SEES the image (perceive) -> run_genesis.
            # Uses GENESIS_MODEL (gpt-4o) -- gpt-4o-mini asks instead of calling run_genesis.
            intent = "genesis"
            mem.system = GENESIS_PERSONA
            injected, lessons = False, []
            answer = await asyncio.to_thread(run_turn, mem, text, img, "image/png", True, 20, True, steps, True, GENESIS_MODEL, allowed_tools=MAKER_TOOLS, on_step=_emit, agent_label="doer")
            learn_line = "GENESIS mode (gpt-4o): vision -> spec -> run_genesis (Maker scoped: master-data only, no planning)"
            # BOARDROOM (behind RIG_BOARD): on a genesis PREVIEW (no write yet), convene the cross-functional
            # panel on the plan -- Engineering / Procurement / Compliance / Finance / Planning each give a
            # GO/NO-GO BEFORE the human confirms. Each persona is a bounded read+advise agent (no writes).
            if BOARD_ON and ORCHESTRATE_ON and not _committed_write(steps):
                _conductor("🪑 convening the function board on the plan…")

                _board_members = []                        # captured for the Board tab of the plan card

                def _on_member(func, phase, txt):
                    if phase == "start":
                        _activity(func.lower(), "phase", text=f"{func} reviewing the plan…")
                    else:                                  # done
                        v = _verdict_of(txt) if txt else ""
                        _board_members.append({"func": func, "vote": v, "note": (txt or "")[:400]})
                        _activity(func.lower(), "reasoning", text=(f"[{v}] " if v else "") + (txt or "")[:700])
                        _status(f"🪑 {func}: {v}")

                plan = (
                    "This is a GENESIS PREVIEW — a PLAN that will be CREATED in SAP only when the user "
                    "confirms. NOTHING is built yet, so do NOT flag objects as 'missing in SAP' (the "
                    "routings, production versions, PIRs, prices and standard costs are all created on "
                    "confirm). Judge ONLY whether the PLAN ITSELF is sound from your function: structure & "
                    "make-vs-buy, sourcing/pricing strategy, compliance coverage, plannability, cost "
                    "sensibility. Flag a real PLAN DEFECT (wrong BOM structure, a made part with no "
                    "sub-assembly BOM in the plan, a bought part the plan gives no vendor/price, a required "
                    "field the plan never intends to set). If the plan is sound and complete, vote GO.\n\n"
                    "--- THE PLAN ---\n" + answer)
                board = await asyncio.to_thread(convene_board, plan, None, False, _on_member)
                for _m, _u in (board.get("usage") or {}).items():   # TELEMETRY: each board member's + chair's tokens
                    _activity(_m.lower(), "usage", tokens_in=_u.get("in", 0),
                              tokens_out=_u.get("out", 0), calls=_u.get("calls", 0))
                go = "BOARD: GO" in (board["verdict"] or "").upper()
                banner = ("🪑 BOARD: GO — the function panel sees no blocker in the plan." if go else
                          "🪑 BOARD: NO-GO — the function panel flagged blockers in the plan (below). Review before you confirm.")
                answer = f"{answer}\n\n---\n### {banner}\n{board['verdict']}"
                learn_line += f" · [board] {'GO' if go else 'NO-GO'}"
                # PRE-GENESIS PLAN CARD: for a FILE preview, render the tabbed contract (Materials|PIRs|Cost|
                # BOMs|Routings|PVs|Board) into the Structured-Data panel -- the decision surface to sign off on.
                _pv = _bom_preview_call(steps)
                if _pv:
                    try:
                        from excel_bom import genesis_from_excel as _gfe
                        from plan_report import plan_report as _plr
                        from plan_card import plan_card as _pcard
                        _pth = _pv[0] if os.path.exists(_pv[0]) else os.path.join(
                            os.path.dirname(os.path.abspath(__file__)), "mcp_server", _pv[0])
                        _spec, _ = await asyncio.to_thread(_gfe, _pth if os.path.exists(_pth) else _pv[0])
                        _pr = await asyncio.to_thread(_plr, _spec, "1710")
                        _bd = {"verdict": "GO" if go else "NO-GO", "text": board.get("verdict", ""),
                               "members": _board_members}
                        steps.append({"author": "board", "kind": "tool_result", "tool": "genesis_plan",
                                      "result": _pcard(_pr["data"], _bd)})
                        _conductor("🧾 Genesis Plan card rendered — review the tabs before you approve")
                    except Exception as _pe:
                        _activity("conductor", "phase", text=f"(plan card unavailable: {type(_pe).__name__}: {_pe})")
        elif is_planning(text):
            # THE PLANNER (Design -> Make -> PLAN): demand + MRP for an ALREADY-MRP-ready material.
            # Scoped to PLANNER_TOOLS -> it structurally CANNOT create/change master data.
            # SESSION ANCHORS (A): FG material + plant are read DETERMINISTICALLY from typed state and
            # pinned into the persona -- after a genesis, "create demand for the FG and run MRP" must
            # never re-ask for them (an anchor present but re-asked is a bug; absent -> asking is right).
            intent = "planning"
            _anch = session_anchors.read(mem.session.dir)
            mem.system = PLANNER_PERSONA + session_anchors.planner_block(_anch)
            injected, lessons = False, []
            _status("📅 planner…")
            answer = await asyncio.to_thread(run_turn, mem, text, img, "image/png", True, CHAT_MAX_STEPS,
                                             False, steps, allowed_tools=PLANNER_TOOLS, on_step=_emitter("planner"), agent_label="planner")
            learn_line = ("PLANNER mode: demand + MRP (scoped — no master-data writes)"
                          + (f" · anchors: FG {_anch.fg_material} @ {_anch.plant}"
                             if _anch and _anch.fg_material else " · anchors: none"))
        else:
            intent = _classify(text)
            learn.capture_correction(st["prev_intent"], text, st["last_answer"])        # capture
            mem.system, injected, lessons = learn.recall_and_inject(                     # recall + inject
                intent, text, BASE_SYSTEM + "\n\n" + _REG.index())
            answer = await asyncio.to_thread(run_turn, mem, text, img, "image/png", True, CHAT_MAX_STEPS, False, steps, allowed_tools=MAKER_TOOLS, on_step=_emit, agent_label="doer")
            learn_line = (f"{len(lessons)} lesson(s) injected" + (" · marker OK" if injected else "")
                          + f" · [mem] {mem.meter()}"
                          + f" · [skills] idx {ntok(_REG.index())}t, {len(_REG.loaded)}/{len(_REG.skills)} bodies")

        # VERIFY + AUTO-HEAL LOOP (behind RIG_ORCHESTRATE): on ANY turn that COMMITTED a write to SAP, a
        # read-only Verifier re-reads SAP and certifies the claim against the SPEC (a BOM for every HALB,
        # not just what the doer claimed). While it finds MISSING (readable, fixable) gaps, the SAME
        # genesis doer is driven to create them and it re-verifies -- capped at HEAL_MAX (the loop-breaker
        # with teeth). UNVERIFIED items (no read tool) are reported but never chased. The fix for the
        # false-complete + half-finished genesis in sessions 903d6806 / 67664336. Default off.
        anchor = _created_materials(steps)
        planned = _planned_material(steps)
        # the verification plant comes from the SESSION ANCHORS (the plant this genesis actually used),
        # not a hardcoded literal; "1710" stays only as the no-anchor fallback.
        _anch_state = session_anchors.read(mem.session.dir)
        _vplant = (_anch_state.plant if _anch_state and _anch_state.plant else "1710")
        if ORCHESTRATE_ON and planned:
            # PLANNING WRITE -> the recursive MRP-TREE validator (the Plan-Verifier). A committed run_mrp
            # produces no created materials, so the master-data verifier can't anchor -- but the MRP RESULT
            # is exactly what needs certifying. This deterministic gate ALWAYS runs after a run_mrp: it walks
            # the whole BOM, reads MD04 per material, and certifies made->planned order / bought->purchase
            # req / demand covered, to any depth. Replaces the old "not independently verified" skip.
            _pmat, _pplant = planned
            _conductor(f"🌳 validating the MRP tree for {_pmat} @ {_pplant} (recursive, deterministic)…")
            try:
                from plan_verifier import verify_mrp_tree
                _res = await asyncio.to_thread(verify_mrp_tree, _pmat, _pplant, _emitter("verifier"))
                answer = f"{answer}\n\n---\n### 🌳 {_res['banner']}\n{_res['report']}"
                learn_line += f" · [mrp-tree] {_res['verdict']}"
                try:                                  # deterministic MRP-tree CARD -> Structured-Data panel
                    steps.append({"author": "verifier", "kind": "tool_result", "tool": "mrp_tree_verification",
                                  "result": verification_cards.mrp_tree_card(_res.get("data") or {})})
                except Exception:
                    pass                              # a card render must never break the turn
            except Exception as _e:
                answer = (f"{answer}\n\n---\n### ⚠️ MRP-tree validation errored ({type(_e).__name__}: {_e}). "
                          f"The MRP run itself is unaffected; re-run the validation.")
                learn_line += " · [mrp-tree] error"
        elif ORCHESTRATE_ON and _committed_write(steps) and not anchor:
            # GUARD: a write happened but no material numbers were produced -> we cannot anchor the
            # verifier to a scope. Do NOT verify/heal (an unanchored verifier could grab the wrong
            # product). Surface it honestly instead of healing blind.
            _conductor("⚠️ verify skipped — no created material numbers to anchor verification")
            answer = (f"{answer}\n\n---\n### ⚠️ Not independently verified\nThe write produced no material "
                      f"numbers I could anchor a SAP read-back to, so I did NOT run the verifier (it must "
                      f"never guess a scope). Re-run so the genesis reports its created material numbers.")
            learn_line += " · [verify] skipped (no anchor)"
        elif ORCHESTRATE_ON and anchor:
            # Fire whenever a genesis actually CREATED materials -- the anchor IS the proof it committed,
            # independent of how the confirm flag was recorded (the file-driven load_bom_from_file commit
            # didn't register as _committed_write, so the deterministic verify silently skipped -- session
            # feb1aa32). _created_materials mines only create-tool RESULTS, so a preview (creates nothing)
            # leaves anchor empty and never trips this.
            _verifier_emit = _emitter("verifier")
            _conductor(f"🔍 verifying {len(anchor)} material(s) against SAP (deterministic, ~0 tokens)…")
            passed, missing, unverified, verdict, vdata = await asyncio.to_thread(verify_genesis_objects, anchor, _vplant, _verifier_emit)
            heals, steer_notes, dropped, stopped = 0, [], set(), False
            while (not passed) and missing > 0 and heals < HEAL_MAX:
                notes, stop = await _drain_steer()   # /btw guidance the user typed mid-run
                if notes:
                    steer_notes.extend(notes)
                    for n in notes:                  # "/btw drop 13449" -> remove from scope so the loop converges
                        if re.search(r"drop|skip|ignore|isn'?t real|not real|phantom|remove", n, re.I):
                            dropped.update(_MATNUM.findall(n))
                    _activity("conductor", "phase", text="↪ steering applied: " + "; ".join(notes))
                if stop:
                    stopped = True
                    _conductor("⏹ steering: STOP — halting the heal loop on your request")
                    break
                heals += 1
                gaps = _gap_summary(verdict)
                _conductor(f"⚠️ {missing} gap(s)" + (f": {gaps}" if gaps else "") + f" — 🔧 auto-healing, pass {heals}/{HEAL_MAX}…")
                hs = []
                answer = await asyncio.to_thread(run_turn, mem, _heal_prompt(verdict, steer_notes), None, "image/png",
                                                 True, 20, True, hs, False, GENESIS_MODEL, _HEAL_TOOLS, _emit, "doer")
                steps.extend(hs)
                anchor = [a for a in _created_materials(steps) if a not in dropped]   # newly-created join; dropped phantoms leave
                _conductor(f"🔍 re-verifying against SAP (after heal {heals}, deterministic)…")
                passed, missing, unverified, verdict, vdata = await asyncio.to_thread(verify_genesis_objects, anchor, _vplant, _verifier_emit)
            if stopped:
                banner = (f"⏹ Healing STOPPED on your request after {heals} pass(es). "
                          f"{missing} object(s) were still MISSING when you stopped.")
            elif passed:
                banner = "✅ INDEPENDENTLY VERIFIED against SAP" + (f" — auto-healed in {heals} pass(es)" if heals else "")
            elif missing > 0:
                banner = (f"❌ STILL INCOMPLETE after {heals} auto-heal pass(es) — {missing} object(s) remain "
                          f"MISSING in SAP. Do NOT trust any 'complete' above.")
            else:
                banner = (f"⚠️ Everything readable is VERIFIED; {unverified} object(s) could NOT be read after "
                          f"retries (a read-availability hiccup, NOT a confirmed gap) — re-run to re-read them.")
            answer = f"{answer}\n\n---\n### 🔍 {banner}\n{verdict}"
            learn_line += f" · [verify] {'PASS' if passed else ('missing='+str(missing) if missing else 'unverified='+str(unverified))} · heals={heals}"
            try:                                      # deterministic genesis-verification CARD -> Structured-Data panel
                steps.append({"author": "verifier", "kind": "tool_result", "tool": "genesis_verification",
                              "result": verification_cards.genesis_card(vdata)})
            except Exception:
                pass                                  # a card render must never break the turn
            # LEDGER: fold every material the verifier actually confirmed into the typed created ledger
            # (heals included), so later reconciliations/questions read the same state.
            try:
                session_anchors.add_created(mem.session.dir,
                                            [r["mat"] for r in (vdata or {}).get("rows", [])] or anchor)
            except Exception:
                pass
            # CONFORMANCE + MANIFEST RECONCILIATION: presence+heal ensured existence of what was CREATED;
            # now audit ACTUAL SAP vs the INTENDED contract -- automatically, for EVERY genesis. The spec
            # comes from the committed BOM file when there is one, else from the SESSION ANCHORS (the
            # spec anchored at preview/commit -- this is what makes IMAGE genesis reconcile too, instead
            # of the created-anchored false-green). The reconciliation is the SOLE source of "complete":
            # a created-set verify can never see the 13 objects that were never created; the manifest can.
            _cspec, _csrc = None, ""
            _cpath = _committed_bom_path(steps)
            if _cpath:
                try:
                    from excel_bom import genesis_from_excel as _cgfe
                    _cp = _cpath if os.path.exists(_cpath) else os.path.join(
                        os.path.dirname(os.path.abspath(__file__)), "mcp_server", _cpath)
                    _cspec, _ = await asyncio.to_thread(_cgfe, _cp if os.path.exists(_cp) else _cpath)
                    _csrc = f"BOM file {os.path.basename(_cpath)}"
                except Exception:
                    _cspec = None
            if _cspec is None:
                _anch_state = session_anchors.read(mem.session.dir)   # re-read: the commit just anchored it
                _cspec = session_anchors.spec_of(_anch_state)
                _csrc = "session-anchored manifest"
            if _cspec is not None:
                _conductor(f"🧾 conformance + manifest reconciliation — actual SAP vs the approved plan ({_csrc})…")
                try:
                    from conformance import verify_conformance as _vconf
                    from plan_card import conformance_card as _ccard
                    _cok, _cdiffs, _crep, _cdata = await asyncio.to_thread(
                        _vconf, _cspec, anchor, _vplant, _emitter("verifier"))
                    _crec = _cdata.get("reconciliation") or {}
                    if _crec and not _crec.get("complete", True):
                        _cbanner = (f"⛔ INCOMPLETE vs the manifest — {len(_crec.get('missing') or [])} of "
                                    f"{_crec.get('planned')} planned object(s) were NEVER CREATED. "
                                    f"Any 'complete' above is void.")
                    elif _cok:
                        _cbanner = "✅ COMPLETE & CONFORMS — every planned object created; SAP state matches the approved plan"
                    else:
                        _cbanner = (f"❌ {_cdata['diffs']} field(s) DO NOT conform to the plan "
                                    f"(drift/missing presence can't see — see the Conformance card)")
                    answer = f"{answer}\n\n---\n### 🧾 {_cbanner}\n{_crep}"
                    learn_line += (f" · [reconcile] {_crec.get('created', '?')}/{_crec.get('planned', '?')}"
                                   f" · [conformance] {'PASS' if _cok else str(_cdata['diffs'])+' diff'}")
                    steps.append({"author": "verifier", "kind": "tool_result", "tool": "conformance",
                                  "result": _ccard(_cdata)})
                except Exception as _ce:
                    answer = f"{answer}\n\n---\n### ⚠️ Conformance audit errored ({type(_ce).__name__}: {_ce})"
            else:
                _conductor("⚠️ no manifest to reconcile against (no anchored spec, no BOM file) — completion NOT certified")
                answer = (f"{answer}\n\n---\n### ⚠️ Completion not certified\nObjects that were created "
                          f"verified against SAP, but no manifest is anchored for this genesis, so "
                          f"created-vs-planned reconciliation could not run — a silent under-delivery "
                          f"would be invisible. Re-run the genesis through its preview so the manifest anchors.")

        st["last_answer"], st["prev_intent"] = answer, intent
        _prev = _bom_preview_call(steps)              # a BOM-file PREVIEW this turn -> remember it so the next
        if _prev:                                     # 'go ahead' commits the SAME parsed spec deterministically
            st["pending_bom"] = {"path": _prev[0], "enrich": _prev[1]}
        learning = {"line": learn_line, "injected": len(lessons), "avoided": 0, "repeated": 0}
        # PERSIST this turn's activity (intent + tool steps) so the Agent-Activity + Structured-Data panels
        # survive a browser refresh -- /api/sessions/{id}/trace serves it back on reload. (The live 💭
        # reasoning chain is not persisted; the tool steps + cards are.)
        try:
            with (mem.session.dir / "activity.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"intent": intent, "steps": steps, "chain": chain_log,
                                    "learning": learning}, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass
        await websocket.send_text(json.dumps({
            "type": "turn", "intent": intent, "answer": answer,
            "trace": steps, "data": _cards(steps), "gate": None, "learning": learning}))
        # AFTER responding (off the user's latency path): refresh the AI title, THEN persist the session
        # + lessons/skills to S3 (so title.json rides along). Both best-effort; never block or break.
        async def _post_turn(sess):
            try:
                session_meta.touch(sess)                          # wall-clock stamp for this turn (meta.json)
                await asyncio.to_thread(ensure_title, sess)        # one small AI Core call, cached
                await asyncio.to_thread(s3_store.persist_turn, sess)  # push changed files (no-op if S3 off)
            except Exception:
                pass
        try:
            asyncio.create_task(_post_turn(mem.session))
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    print("D2M Test Rig UI  ->  http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
