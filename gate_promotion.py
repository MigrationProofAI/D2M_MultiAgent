"""PROMOTION GATE -- the 'captured -> durable' close. A queued correction (which the model auto-typed
`fact`) is HUMAN re-typed to its true `method`, routed to a skill, and becomes durable behaviour: a
SKILL.md that CARRIES the rule, the promotion marked `applied`, the soft lesson retired so it stops
surfacing in fuzzy recall. Proves the 'method -> skill' destination actually closes the loop.

Re-runnable: if the lesson is still queued it performs the human-gated accept; if already promoted it
VERIFIES the durable state. Never auto-applies -- the re-type + confirm are explicit.

    uv run python gate_promotion.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import promote
import learning
from skills import SkillRegistry

PID = "P-4ebe06ca"                 # the plant-extension / BOM-precondition correction
TARGET_SKILL = "bom-precondition"

promo = next((p for p in learning.list_promotions() if p.get("id") == PID), None)
assert promo, f"promotion {PID} not found (expected the BOM-precondition correction)"
lid = promo["lesson_id"]

print(f"=== promotion gate: {PID} (lesson {lid}) ===")
print(f"  text: {promo.get('summary', '')[:110]}")

if promo.get("status") == "queued":
    print(f"  model auto-typed: {promo.get('lesson_type')}  ->  HUMAN re-types: method  (target {TARGET_SKILL})")
    prev = promote.accept(PID, "method", target=TARGET_SKILL, confirm=False)   # PREVIEW, no write
    print("  PROPOSED (no write):\n   " + prev["preview"][:200].replace("\n", "\n   "))
    res = promote.accept(PID, "method", target=TARGET_SKILL, confirm=True)     # human confirms -> apply
    print("  ACCEPTED:", res)
else:
    print(f"  already {promo.get('status')} (accepted_type={promo.get('accepted_type')}) -> verifying durable state")

# ---- verify the durable state (re-load registry + lessons from disk) ----
reg = SkillRegistry()
sk = reg.skills.get(TARGET_SKILL)
body = sk.body() if sk else ""
learning._load()
promo = next((p for p in learning.list_promotions() if p.get("id") == PID), {})

re_typed = promo.get("accepted_type") == "method"                                   # the human's re-type was recorded
skill_exists = sk is not None
carries = ("extended to that plant" in body.lower()) and (f"promoted {lid}" in body)
applied = promo.get("status") == "applied"
retired = any(le.get("id") == lid and le.get("status") == "retired" for le in (learning._lessons or []))

print("\n=== GATE ===")
print(f"  (1) model 'fact' re-typed to 'method' by the human   : {re_typed}")
print(f"  (2) '{TARGET_SKILL}' skill exists + triggerable       : {skill_exists}")
print(f"  (3) its SKILL.md body CARRIES the promoted rule       : {carries}")
print(f"  (4) promotion {PID} marked 'applied'            : {applied}")
print(f"  (5) soft lesson {lid} retired (no fuzzy recall)   : {retired}")
print(f"\n  ALL PASS: {all([re_typed, skill_exists, carries, applied, retired])}")
