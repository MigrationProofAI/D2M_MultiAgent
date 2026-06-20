"""Step 1 GATE -- prove the stripped spine survived: create ONE material and read it back, through the
hand-rolled loop (no ADK). If this passes end-to-end, the substance is intact and we can build on it.

    uv run python gate_step1.py
"""
from dotenv import load_dotenv
load_dotenv()

from agent import run_agent

SI = ("You are a SAP S/4HANA master-data assistant. Use the tools to do exactly what is asked, step "
      "by step. To CREATE a material: call build_material_payload, then create_material with "
      "confirm=true to commit. Then READ it back with get_material and report the new material ID and "
      "its ProductType. Be concise.")

USER = ("Create a trading good (HAWA): description 'RIG TEST WIDGET', base unit EA, product group "
        "L001, plant 1710. Commit it, then read it back and report the new material ID and type.")

if __name__ == "__main__":
    print("=== Step 1 gate: create + read one material through the stripped loop ===\n")
    final, msgs = run_agent(SI, USER, max_steps=10)
    tool_results = sum(1 for m in msgs if m.get("role") == "tool")
    print("\n=== FINAL ===\n" + final)
    print(f"\n[spine] {len(msgs)} messages, {tool_results} tool result(s) dispatched by the hand-rolled loop")
