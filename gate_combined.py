"""COMBINED GATE -- memory + skills + learning in ONE run, proving they hold SIMULTANEOUSLY and do
NOT break each other. The isolated gates (step2/3/5) are necessary but not sufficient; this is the
interaction proof -- the failure mode that bit old D2M (compaction colliding with a live multi-step
run). Passing this is what licenses porting the engine elsewhere.

Asserts, in one session:
  (1) a skill triggered; index stayed tiny; only the triggered body loaded
  (2) compaction FIRED mid-session and the session did NOT hollow out
  (3) an early fact (pre-compaction) is still recalled AFTER compaction (from the summary)
  (4) a correction was captured mid-session -> a lesson
  (5) that learning is recalled + injected in a genuinely FRESH process (marker-confirmed)
  (6) NO interaction failure: the skill index survived compaction, the injected LESSONS block survived
      compaction, and the triggered skill stayed tracked + re-loadable (index intact). << the whole point

    uv run python gate_combined.py            # runs the session, then spawns a fresh process for (5)
    uv run python gate_combined.py apply      # fresh-process recall+inject only (spawned by the gate)
"""
import os
import sys
import json
import subprocess
from dotenv import load_dotenv
load_dotenv()

import learn
import learning
from memory import ntok

INTENT = "create_change"
SEED = ("No, that's wrong -- before a plant's BOM, the finished good AND every component must be "
        "extended to plant 1710 first.")


# ---- fresh-process apply mode: learning reloads from disk, then recalls + injects (item 5) ----
def session2_apply():
    learning._load()
    SI = "You are a SAP master-data assistant. Apply any LESSONS injected into your instructions."
    query = "I'm about to add components to a BOM for a new assembly in plant 1710 -- what should I check first?"
    system, injected, lessons = learn.recall_and_inject(INTENT, query, SI)
    print("APPLY_RESULT " + json.dumps({
        "injected": injected, "n": len(lessons),
        "marker": learn.LESSON_MARKER in system}))


if len(sys.argv) > 1 and sys.argv[1] == "apply":
    session2_apply()
    sys.exit(0)


# ---- the combined session (memory + skills + learning, one process) ----
from run_session import run_session

print("=== COMBINED gate: memory + skills + learning, one session ===\n")
r = run_session(intent=INTENT, seed_correction=SEED, budget=500, min_working=4, verbose=True)
mem, reg, sess = r["mem"], r["reg"], r["sess"]

# ---- (5) cross-session: a genuinely fresh process recalls + injects ----
print("\n[item 5] spawning a FRESH process to recall + inject...")
proc = subprocess.run([sys.executable, __file__, "apply"], capture_output=True, text=True, cwd=os.getcwd())
line = next((x for x in proc.stdout.splitlines() if x.startswith("APPLY_RESULT")), None)
if not line:
    print("  STDERR:", proc.stderr[-400:])
fresh = json.loads(line.split(" ", 1)[1]) if line else {}
print("  fresh-process recall:", fresh)

# ---- assertions ----
idx_tok = ntok(reg.index())
full_tok = sum(ntok(s.body()) for s in reg.skills.values())
loaded = reg.loaded
loaded_name = next(iter(loaded), None)

# (1) skills: triggered, tiny index, only the triggered body loaded
a1 = (len(loaded) >= 1) and (len(loaded) < len(reg.skills)) and (idx_tok < full_tok)

# (2) compaction fired mid-session, no hollow-out (working still has the floor of recent turns)
a2 = (mem.summary_tokens() > 0) and (sess.archived_count() > 0) and (len(mem.working) >= mem.min_working)

# (3) early fact recalled AFTER compaction (from the summary)
ra = (r["recall_answer"] or "").upper()
a3 = ("BLUEJAY" in ra) and ("1710" in ra)

# (4) lesson captured mid-session
a4 = bool(r["captured_lesson"])

# (5) recalled + injected in a fresh process, marker confirmed
a5 = (fresh.get("n", 0) > 0) and bool(fresh.get("injected")) and bool(fresh.get("marker"))

# (6) INTERACTION -- the things compaction must NOT silently drop:
index_intact = reg.index() in mem.system                     # skill index lives in system -> never compacted
injection_survived = learn.LESSON_MARKER in mem.system        # injected LESSONS block in system survived
skill_tracked = bool(loaded_name) and (loaded_name in reg.loaded) and index_intact   # triggered skill still re-loadable
a6 = index_intact and injection_survived and skill_tracked

print("\n=== GATE ===")
print(f"  (1) skill triggered, index small ({idx_tok} tok), only triggered loaded ({len(loaded)}/{len(reg.skills)}): {a1}")
print(f"  (2) compaction fired mid-session, no hollow-out (working={len(mem.working)})                 : {a2}")
print(f"  (3) early fact recalled AFTER compaction                                                     : {a3}")
print(f"  (4) lesson captured mid-session ({(r['captured_lesson'] or {}).get('id')})                          : {a4}")
print(f"  (5) lesson recalled+injected in a FRESH process (marker)                                     : {a5}")
print(f"  (6) interaction: index intact={index_intact}, injection survived={injection_survived}, "
      f"skill re-loadable={skill_tracked}                                                              : {a6}")
print(f"\n  ALL PASS: {all([a1, a2, a3, a4, a5, a6])}")
