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
import json
import base64
import asyncio
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from session import Session, SESSIONS_DIR
from memory import TieredMemory, ntok
from skills import SkillRegistry
from tools import set_skill_registry, set_current_session
from agent import run_turn
from genesis_mode import GENESIS_PERSONA, is_genesis
from model_client import GENESIS_MODEL
import learn

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


# ---- serve the built React app ----
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/assets", StaticFiles(directory=str(STATIC / "assets")), name="assets")


# ---- stub the /api endpoints the React app pings on load (so panels don't error) ----
@app.get("/api/sessions")
def _sessions():
    """List persisted rig sessions (newest first) for the Sessions browser."""
    out = []
    if SESSIONS_DIR.exists():
        dirs = [d for d in SESSIONS_DIR.iterdir() if d.is_dir() and (d / "trace.jsonl").exists()]
        for d in sorted(dirs, key=lambda p: p.stat().st_mtime, reverse=True):
            turns = Session(d.name).reload_turns()
            title = next((t["text"][:70] for t in turns if t["role"] == "user" and t.get("text")), "(session)")
            out.append({"id": d.name, "title": title, "turns": sum(1 for t in turns if t["role"] == "user")})
    return out


@app.get("/api/sessions/{sid}/events")
def _events(sid):
    """Reload a session's chat from disk -> the UI re-renders it on restart / switch."""
    return [{"role": t["role"], "text": t["text"], "image": True if t.get("image") else None}
            for t in Session(sid).reload_turns()]


@app.get("/api/sessions/{sid}/trace")
def _trace(sid):
    return []


@app.get("/api/kg")
def _kg():
    return {"nodes": [], "edges": []}


@app.post("/api/explain")
async def _explain(payload: dict = None):
    return {"text": "(rig) explanations aren't wired -- this is the clean-room test rig."}


@app.post("/api/explain_app")
async def _explain_app(payload: dict = None):
    return {"sections": []}


@app.post("/api/tts")
async def _tts(payload: dict = None):
    return JSONResponse({"error": "tts not in rig"}, status_code=404)


# ---- the chat: D2M's WS protocol, our hand-rolled loop behind it ----
@app.websocket("/ws/{sid}")
async def ws(websocket: WebSocket, sid: str):
    await websocket.accept()
    st = _state(sid)
    while True:
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
        if not text and not img:
            continue

        await websocket.send_text(json.dumps({"type": "status", "text": "working…"}))
        mem = st["mem"]
        set_current_session(mem.session)              # so write_skill_artifact / promote_skill know the session
        steps = []
        if is_genesis(text, img is not None):
            # DESIGN2MAKE: genesis persona + the vision model SEES the image (perceive) -> run_genesis.
            # Uses GENESIS_MODEL (gpt-4o) -- gpt-4o-mini asks instead of calling run_genesis.
            intent = "genesis"
            mem.system = GENESIS_PERSONA
            injected, lessons = False, []
            answer = await asyncio.to_thread(run_turn, mem, text, img, "image/png", True, 20, True, steps, True, GENESIS_MODEL)
            learn_line = "GENESIS mode (gpt-4o): vision -> spec -> run_genesis (preview, then confirm to write)"
        else:
            intent = _classify(text)
            learn.capture_correction(st["prev_intent"], text, st["last_answer"])        # capture
            mem.system, injected, lessons = learn.recall_and_inject(                     # recall + inject
                intent, text, BASE_SYSTEM + "\n\n" + _REG.index())
            answer = await asyncio.to_thread(run_turn, mem, text, img, "image/png", True, CHAT_MAX_STEPS, False, steps)
            learn_line = (f"{len(lessons)} lesson(s) injected" + (" · marker OK" if injected else "")
                          + f" · [mem] {mem.meter()}"
                          + f" · [skills] idx {ntok(_REG.index())}t, {len(_REG.loaded)}/{len(_REG.skills)} bodies")
        st["last_answer"], st["prev_intent"] = answer, intent
        await websocket.send_text(json.dumps({
            "type": "turn", "intent": intent, "answer": answer,
            "trace": steps, "data": _cards(steps), "gate": None,
            "learning": {"line": learn_line, "injected": len(lessons), "avoided": 0, "repeated": 0}}))


if __name__ == "__main__":
    import uvicorn
    print("D2M Test Rig UI  ->  http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
