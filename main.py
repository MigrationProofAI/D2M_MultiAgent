"""main.py -- the rig's interactive CLI ("UI"). The rig is headless by design (the brief: CLI, meters
to stdout; the ADK WebSocket server + React frontend were stripped in Step 1). This is how you drive
it by hand -- and it exercises ALL THREE capabilities together in one loop:

  * tiered memory  -- compaction on a token budget + a per-turn meter; images evicted to disk
  * skills         -- progressive disclosure (index in context, body on trigger, scripts executed)
  * learning loop  -- recall past lessons + inject them (marker-confirmed) + capture corrections

    uv run python main.py

Commands:
    /image <path>   attach an image (evicted to assets/ on your next message)
    /reflect        capture durable lessons from this session
    /promotions     show the human-gated promotion queue
    /meter          show the memory + skills meters now
    /reset          start a fresh session
    /quit
"""
import os
from dotenv import load_dotenv
load_dotenv()

from session import Session
from memory import TieredMemory, ntok
from skills import SkillRegistry
from tools import set_skill_registry
from agent import run_turn
import learn

BASE_SYSTEM = ("You are a SAP master-data assistant in a clean-room rig. Use your tools and skills. "
               "When a task matches a skill, call load_skill(name) first. Apply any injected LESSONS.")


def classify(text: str) -> str:
    """A trivial intent tag (the rig has no router) -- enough to scope learning recall."""
    t = text.lower()
    if any(w in t for w in ("create", "material", "bom", "component", "plant", "extend", "routing", "pir")):
        return "create_change"
    return "assist"


def new_session():
    sess = Session("live-" + os.urandom(3).hex())
    # RIG_BUDGET lets you watch compaction fire interactively: e.g. set RIG_BUDGET=400 and chat a bit,
    # the [memory] meter will show working drop while summary/archived grow.
    budget = int(os.getenv("RIG_BUDGET", "4000"))
    mem = TieredMemory(sess, system=BASE_SYSTEM, budget=budget, min_working=6)
    return sess, mem


def main():
    reg = SkillRegistry()
    set_skill_registry(reg)
    sess, mem = new_session()
    last_answer, prev_intent, pending_image = "", "assist", None

    print(f"=== D2M Test Rig - interactive CLI (session {sess.id}) ===")
    print("skills:", list(reg.skills))
    print("type a message, or: /image <path>  /reflect  /promotions  /meter  /reset  /quit\n")

    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line == "/quit":
            break
        if line == "/meter":
            print("   [memory]", mem.meter())
            print("   [skills]", reg.meter(ntok))
            continue
        if line == "/promotions":
            ps = learn.promotions()
            print(f"   {len(ps)} promotion(s):")
            for p in ps:
                print(f"     {p.get('status')} [{p.get('lesson_type')}] -> {p.get('proposed_artifact')} | {(p.get('summary') or '')[:60]}")
            continue
        if line == "/reset":
            sess, mem = new_session()
            last_answer, prev_intent, pending_image = "", "assist", None
            print("   new session:", sess.id)
            continue
        if line.startswith("/image "):
            path = line[7:].strip().strip('"')
            try:
                pending_image = open(path, "rb").read()
                print(f"   [{len(pending_image)} bytes attached - evicted to assets/ on your next message]")
            except Exception as e:
                print("   image error:", e)
            continue
        if line == "/reflect":
            steps = [{"kind": "text", "text": m.get("content", "")} for m in mem.working if m.get("content")]
            kept = learn.reflect(prev_intent, steps, "reflect")
            print(f"   captured {len(kept)} lesson(s)")
            continue

        # --- a normal turn: learning capture + recall/inject, then the memory+skills loop ---
        intent = classify(line)
        learn.capture_correction(prev_intent, line, last_answer)
        mem.system, injected, lessons = learn.recall_and_inject(intent, line, BASE_SYSTEM + "\n\n" + reg.index())
        answer = run_turn(mem, line, image=pending_image, mime="image/png", tools=True, verbose=True)
        pending_image = None
        last_answer, prev_intent = answer, intent

        print("\nbot>", answer)
        learn_line = f"{len(lessons)} lesson(s) injected" + (" [marker confirmed]" if injected else "")
        print(f"   [memory]   {mem.meter()}")
        print(f"   [skills]   {reg.meter(ntok)}")
        print(f"   [learning] {learn_line}\n")

    print("bye - session saved at", sess.dir)


if __name__ == "__main__":
    main()
