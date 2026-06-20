"""run_session.py -- the WHOLE engine in ONE continuous session: tiered memory + skills + learning,
wired together. The isolated gates (step2 compaction, step3 skills, step5 learning) each prove one
capability alone; this proves they hold SIMULTANEOUSLY and do not break each other -- the interaction
failure mode that bit the old D2M (compaction + memory + a live run colliding).

Key invariants this flow sets up so `gate_combined.py` can assert them:
  * the skill INDEX and the injected LESSONS block live in `system` -- which `maybe_compact` never
    touches (it only evicts `working`). So both must survive a compaction event.
  * a triggered skill's BODY lands in `working` (compactable) but stays recoverable via `reg.loaded`,
    the on-disk archive, and the intact index.
  * an early fact, evicted into the summary by compaction, is still recallable.
"""
import os

from session import Session
from memory import TieredMemory, ntok
from skills import SkillRegistry
from tools import set_skill_registry
from agent import run_turn
import learn                                   # importing this sets learning.ENABLED = True (the rig always learns)

BASE_SYSTEM = ("You are a SAP master-data assistant in a clean-room rig. Use your tools and skills. "
               "When a task matches a skill, call load_skill(name) FIRST, then follow its instructions.")


def run_session(intent: str = "create_change", budget: int = 500, min_working: int = 4,
                seed_correction: str | None = None, verbose: bool = True) -> dict:
    """Run one continuous session that exercises memory + skills + learning together. Returns the live
    `mem`, `reg`, `sess` plus the captured lesson and the early-fact recall answer, for assertion."""
    reg = SkillRegistry()
    set_skill_registry(reg)
    sess = Session("combined-" + os.urandom(3).hex())

    # (a) LEARNING -- seed a relevant lesson, then RECALL + INJECT it into the SYSTEM instruction (the
    #     same place the skill index lives). This is what must survive compaction later.
    if seed_correction:
        learn.capture_correction(intent, seed_correction, "(the agent's prior wrong step)")
    system = BASE_SYSTEM + "\n\n" + reg.index()
    system, injected, lessons = learn.recall_and_inject(
        intent, "extend the components and build the BOM in a plant", system)

    mem = TieredMemory(sess, system=system, budget=budget, min_working=min_working)
    steps: list = []

    def turn(tag, q, **kw):
        ans = run_turn(mem, q, tools=kw.pop("tools", True), steps=steps, verbose=False, **kw)
        if verbose:
            print(f"{tag}: {ans.strip()[:64]}")
            print("      " + mem.meter())
        return ans

    if verbose:
        print(f"=== run_session (session {sess.id}) ===")
        print(f"start: lessons injected at start = {injected} ({len(lessons)}); "
              f"skills index = {ntok(reg.index())} tok\n")

    # (1) EARLY FACT -- evicted by compaction later, recalled at the end from the summary
    turn("T1  ", "Remember for later: the project codename is BLUEJAY and the target plant is 1710. "
                 "Just acknowledge.", max_steps=2)

    # (2) SKILL TRIGGER -- exactly one skill's body loads (progressive disclosure)
    turn("T2  ", "I need to create a new trading good (HAWA) called 'Hinge Bracket' in plant 1710. "
                 "Load the right skill FIRST with load_skill, then give me the steps -- don't create it.",
         max_steps=4)
    loaded_after_skill = list(reg.loaded)

    # (3) FILLER -- push past the token budget so compaction FIRES mid-session
    for i, q in enumerate([
            "Explain a bill of materials in two sentences.",
            "List four SAP material types, one line each.",
            "Describe MRP type PD in two sentences.",
            "What is a valuation class? Answer in two sentences.",
            "Give a one-line analogy for a routing."], start=3):
        turn(f"T{i}  ", q, tools=False, max_steps=2)

    # (4) MID-SESSION CORRECTION -- a lesson is captured DURING the live session
    captured = learn.capture_correction(
        intent,
        "No, that's wrong -- every BOM component must be plant-extended to 1710 BEFORE you add it to the BOM.",
        "I'll add the components to the BOM now.")
    if verbose:
        print(f"\nmid-session correction captured -> lesson {captured['id'] if captured else None}")

    # (5) EARLY-FACT RECALL -- from the summary, since T1 was evicted by compaction
    recall_ans = turn("Tfin", "From earlier in this session: what is the project codename, and the target plant?",
                      tools=False, max_steps=2)
    if verbose:
        print(f"\nRECALL: {recall_ans.strip()[:120]}")
        print("final meter: " + mem.meter())

    return {
        "sess": sess, "mem": mem, "reg": reg,
        "injected_at_start": injected, "lessons_at_start": lessons,
        "loaded_after_skill": loaded_after_skill,
        "captured_lesson": captured, "recall_answer": recall_ans, "steps": steps,
    }
