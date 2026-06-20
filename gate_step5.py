"""Step 5 GATE -- the learning loop, the CROSS-SESSION proof:
  (1) session 1: a correction is captured -> a lesson is written to lessons.jsonl;
  (2) session 2 -- a genuinely FRESH PROCESS -- recalls that lesson and INJECTS it, with a
      request-level marker confirming the LESSONS block reached the outgoing system instruction;
  (3) the correction populates the human-gated promotion queue.

    uv run python gate_step5.py            # orchestrates session 1, then spawns session 2 as a fresh process
    uv run python gate_step5.py apply      # session 2 only (spawned by the orchestrator)
"""
import os
import sys
import json
import subprocess
from dotenv import load_dotenv
load_dotenv()

import learn
import learning

INTENT = "create_change"
SI = "You are a SAP master-data assistant. Apply any LESSONS injected into your instructions."


def session2_apply():
    """A FRESH PROCESS: learning reloads lessons.jsonl from disk, then recalls + injects."""
    learning._load()
    query = "I'm about to add components to the BOM for a new assembly in plant 1710 -- what should I check first?"
    system, injected, lessons = learn.recall_and_inject(INTENT, query, SI)
    print("APPLY_RESULT " + json.dumps({
        "injected": injected,
        "n": len(lessons),
        "texts": [(l.get("correction") or l.get("mistake_or_insight")) for l in lessons],
        "marker_in_system": learn.LESSON_MARKER in system,
    }))


if len(sys.argv) > 1 and sys.argv[1] == "apply":
    session2_apply()
    sys.exit(0)

# ---- Session 1: TEACH (a correction -> lesson + promotion) ----
print("=== Step 5 gate: learning loop, cross-session ===\n")
l1 = learn.capture_correction(
    INTENT,
    "No, that's wrong -- every BOM component must be extended to plant 1710 BEFORE you add it to the BOM.",
    "I'll add the components to the BOM now.")
print(f"[session 1] correction captured -> lesson {l1['id'] if l1 else None}")
learn.capture_correction(           # a recurrence reinforces it
    INTENT,
    "Wrong again -- components have to be plant-extended first, then added to the BOM.", "ok")

# ---- Session 2: APPLY in a genuinely fresh process ----
print("[session 2] spawning a FRESH process to recall + inject...\n")
proc = subprocess.run([sys.executable, __file__, "apply"], capture_output=True, text=True, cwd=os.getcwd())
line = next((x for x in proc.stdout.splitlines() if x.startswith("APPLY_RESULT")), None)
res = json.loads(line.split(" ", 1)[1]) if line else {}
if not line:
    print("STDERR:", proc.stderr[-400:])
print("fresh-process recall:", json.dumps(res, indent=2)[:500])

# ---- promotion queue ----
queued = [p for p in learn.promotions() if p.get("status") == "queued"]

# ---- assertions ----
lesson_written = os.path.exists("lessons.jsonl") and os.path.getsize("lessons.jsonl") > 0
recalled = res.get("n", 0) > 0
inj_confirmed = bool(res.get("injected") and res.get("marker_in_system"))
promoted = len(queued) > 0
print("\n=== GATE ===")
print(f"  (1) lesson written in session 1          : {lesson_written}")
print(f"  (2) recalled in a FRESH process          : {recalled}  {res.get('texts')}")
print(f"  (3) injection marker confirmed (request) : {inj_confirmed}")
print(f"  (4) human-gated promotion queue populated: {promoted}  ({len(queued)} queued)")
print(f"\n  ALL PASS: {lesson_written and recalled and inj_confirmed and promoted}")
