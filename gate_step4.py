"""Step 4 GATE -- session as a folder. Most of this was built in Step 2 (session.py: trace/assets/
summary/archive; blobs evicted to assets/). This proves the remaining piece: on RELOAD (a fresh
process reading the folder), a pasted image comes back as an 'image attached' MARKER from the asset,
NOT re-embedded into context.

    uv run python gate_step4.py
"""
import os
from dotenv import load_dotenv
load_dotenv()

from session import Session
from memory import TieredMemory
from agent import run_turn

SID = "step4-gate-" + os.urandom(3).hex()
sess = Session(SID)
mem = TieredMemory(sess, system="You are a helpful assistant.", budget=4000, min_working=6)

# paste an image, then a follow-up text turn
fake_image = os.urandom(50000)                              # 50 KB stand-in
run_turn(mem, "Here is the product photo to register.", image=fake_image, mime="image/png", tools=False)
run_turn(mem, "Thanks -- what material type would you suggest for it?", tools=False)

# --- RELOAD from disk: a brand-new Session object reading the same folder ---
reloaded = Session(SID)
turns = reloaded.reload_turns()
print(f"=== Step 4 gate (session {SID}) -- reloaded {len(turns)} turns from disk ===\n")
img_turn = None
for t in turns:
    marker = t["image"]["marker"] if t.get("image") else ""
    print(f"  [{t['role']}] {t['text'][:48]:48}  {marker}")
    if t.get("image"):
        img_turn = t

assets = os.listdir(reloaded.assets)
trace_bytes = reloaded.trace_file.read_text(encoding="utf-8")
print("\n=== GATE ===")
landed = len(assets) == 1
shows_marker = bool(img_turn and img_turn["image"]["marker"])
on_disk = bool(img_turn and img_turn["image"]["on_disk"])
# The real invariant is EVICTION: the trace carries the short asset REF, never the 50 KB blob. Assert
# that directly -- the ref string is present, there's no base64, and the trace is nowhere near what the
# blob would add (a leak balloons it to 50 KB+; the threshold sits far below that yet far above any text
# turn, so model verbosity can't red this the way the old len<2000 heuristic did).
ref = img_turn["image"]["ref"] if img_turn else ""
ref_in_trace = bool(ref) and ref in trace_bytes
no_blob = "base64" not in trace_bytes and len(trace_bytes) < len(fake_image) // 5   # 10 KB << a 50 KB leak
trace_has_no_bytes = ref_in_trace and no_blob
print(f"  image landed in assets/            : {assets}")
print(f"  reload shows 'image attached'      : {shows_marker}  ({img_turn['image']['marker'] if img_turn else '-'})")
print(f"  asset is on disk, not in context   : {on_disk}")
print(f"  trace.jsonl carries a REF not bytes: {trace_has_no_bytes}  (ref {'present' if ref_in_trace else 'MISSING'}, "
      f"trace {len(trace_bytes)} chars, blob {len(fake_image)})")
print(f"\n  ALL PASS: {landed and shows_marker and on_disk and trace_has_no_bytes}")
