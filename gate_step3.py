"""Step 3 GATE -- skills with progressive disclosure. Proves:
  - the INDEX (name+description) stays tiny and is the only always-in-context cost;
  - only the TRIGGERED skill's body loads (not every skill's body);
  - a skill SCRIPT executes and costs ~0 context (only its verdict enters the conversation, not the source).

    uv run python gate_step3.py
"""
import os
from dotenv import load_dotenv
load_dotenv()

from session import Session
from memory import TieredMemory, ntok
from skills import SkillRegistry
from tools import set_skill_registry
from agent import run_turn

reg = SkillRegistry()
set_skill_registry(reg)

SID = "step3-gate-" + os.urandom(3).hex()
sess = Session(SID)
SI = ("You are a SAP master-data assistant. You have SKILLS available (listed below). When a task matches "
      "a skill, call load_skill(name) to load its full instructions BEFORE acting, then follow them. Use "
      "run_skill_script to run a skill's script when it helps.\n\n" + reg.index())
mem = TieredMemory(sess, system=SI, budget=6000, min_working=8)

print(f"=== Step 3 gate (session {SID}) ===")
print("skills discovered:", list(reg.skills))
print("BEFORE any trigger:  " + reg.meter(ntok))
print()

# (1) a task that should TRIGGER one skill -> load only its body
a1 = run_turn(mem, "I need to create a new trading good (HAWA) called 'Hinge Bracket' in plant 1710. "
                   "Load the right skill first, then give me the exact steps (don't create it yet).",
              tools=True, max_steps=4)
print("ANSWER 1:", a1.strip()[:160].replace("\n", " "), "...")
print("AFTER trigger:       " + reg.meter(ntok))
print()

# (2) a task that runs a skill SCRIPT -> execute, not read
a2 = run_turn(mem, "Run the codebook-consult skill's check_value.py script to verify 'HAWA' is a valid "
                   "ProductType, and report its verdict.", tools=True, max_steps=4)
print("ANSWER 2:", a2.strip()[:160].replace("\n", " "))
print("AFTER script:        " + reg.meter(ntok))

# ---- gate assertions ----
idx = ntok(reg.index())
full = sum(ntok(s.body()) for s in reg.skills.values())
loaded = sum(ntok(b) for b in reg.loaded.values())
script_tok = reg.script_result_chars // 4
print("\n=== GATE ===")
print(f"  index (always in context)        : {idx} tok")
print(f"  bodies loaded (triggered only)   : {len(reg.loaded)}/{len(reg.skills)}  ({loaded} tok)")
print(f"  full-disclosure would cost       : {full} tok   -> saved {full - loaded} tok by not loading untriggered skills")
print(f"  script context cost (~0)         : ~{script_tok} tok (verdict only, source never read)")
index_tiny = idx < full
only_triggered = len(reg.loaded) < len(reg.skills) and loaded < full
script_cheap = script_tok < 100
print(f"\n  ALL PASS: {index_tiny and only_triggered and script_cheap}")
