"""Step 2 GATE -- tiered memory / compaction. Proves, on disk:
  (1) a long session runs past the budget; compaction FIRES and the session does NOT hollow out.
  (2) a fact from EARLY in the session is recalled (from the summary, after its turn was evicted).
  (3) an image is on disk and NOT in context after its turn (token count drops, not multiplies).
  (4) a token meter prints each turn: working | summary | archived(on disk) | image-in-context.

    uv run python gate_step2.py
"""
import os
from dotenv import load_dotenv
load_dotenv()

from session import Session
from memory import TieredMemory
from agent import run_turn

SID = "step2-gate-" + os.urandom(3).hex()          # fresh session each run
sess = Session(SID)
SI = ("You are a helpful assistant with a memory. Answer using the whole conversation, including the "
      "SUMMARY of earlier (compacted) turns. If asked about an earlier fact, recall it from the summary.")
# small budget so compaction fires after a few turns (the dynamics are the point, not the number) --
# 300 forces the early-fact turn (T1) to be evicted into the summary before the final recall turn
mem = TieredMemory(sess, system=SI, budget=300, min_working=4)


def show(tag, ans):
    print(f"{tag}: {ans.strip()[:70]}")
    print("      " + mem.meter())


print(f"=== Step 2 gate (session {SID}) ===")
print("meter = working | summary | archived(on disk) | image-in-context\n")

# (T1) EARLY FACT -- this turn will be evicted later
show("T1 ", run_turn(mem, "Remember: project codename is BLUEJAY, target plant is 1710, lead engineer "
                          "is Dana Okafor. Just acknowledge.", tools=False))

# (T2..) filler turns -> push past the budget -> force compaction
for i, q in enumerate([
        "Explain a bill of materials in three sentences.",
        "List five SAP material types with one line each.",
        "Describe MRP in a short paragraph.",
        "What is a purchasing info record? Two sentences.",
        "Give a short analogy for a routing in manufacturing.",
        "Explain valuation class briefly."], start=2):
    show(f"T{i} ", run_turn(mem, q, tools=False))

# (T_img) IMAGE -> must be evicted to disk, NOT embedded
fake_image = os.urandom(45000)                      # 45 KB stand-in for a pasted photo
show("Timg", run_turn(mem, "Here is the product photo; just note that it was attached.",
                      image=fake_image, mime="image/png", tools=False))

# (T_final) EARLY-FACT RECALL -- from the summary, since T1 was evicted
recall = run_turn(mem, "From earlier: what is the project codename and who is the lead engineer?", tools=False)
print(f"\nRECALL: {recall.strip()}")
print("final meter: " + mem.meter())

# ---- gate assertions ----
compacted = mem.summary_tokens() > 0 and sess.archived_count() > 0
recalled = ("BLUEJAY" in recall.upper()) and ("DANA" in recall.upper() or "OKAFOR" in recall.upper())
img_ref = next((p for p in os.listdir(sess.assets)), None)
img_on_disk = img_ref is not None
img_not_in_ctx = not mem.image_in_context()
print("\n=== GATE ===")
print(f"  (1) compaction fired (summary>0 & archived>0): {compacted}")
print(f"  (2) early-fact recall from summary           : {recalled}")
print(f"  (3) image on disk ({img_ref})        : {img_on_disk}")
print(f"  (4) image NOT in context                     : {img_not_in_ctx}")
print(f"\n  ALL PASS: {compacted and recalled and img_on_disk and img_not_in_ctx}")
