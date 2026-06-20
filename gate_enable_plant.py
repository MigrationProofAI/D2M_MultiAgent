"""GATE -- B6 one-call plant enablement. enable_plant_production orchestrates the whole manual
sequence (extend FG + components -> work-scheduling -> planning MRP + grounded controller -> BOM ->
routing on a grounded work center -> production version -> optional demand/MRP) as ONE tool, with
grounding built in. This proves the PLAN (confirm=false): it grounds the controller + work center for
the plant, resolves the components, lays out the ordered steps, and writes NOTHING -- and every
ungrounded-plant path ABORTS before any write. (The grounding + reads are stubbed so the gate runs
offline and deterministically; the confirm=true writes are exercised live, not here.)

    uv run python gate_enable_plant.py
"""
import sys, json
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "mcp_server")

import genesis, make, config_graph

# --- stub the grounding + reads so the gate is offline + deterministic ---
config_graph.get_relation = lambda rel, plant: (
    {"plant": plant, "relationship": rel,
     "values": [{"code": "002", "text": "Julia Nadel"}, {"code": "003", "text": "Other"}]}
    if rel == "mrp_controller" else {"values": []})
config_graph.validate_plant_config = lambda plant, **kw: []
make._load_work_centers = lambda: {"1010": [{"work_center": "1010_WC", "desc": "Assembly"}]}
make._resolve_work_center = lambda name, plant: ("999", []) if name else (None, [])
genesis._source_bom_components = lambda mat, plant: [{"component": "11163", "quantity": 2},
                                                     {"component": "11164", "quantity": 1}]
genesis._exists = lambda m: True

writes = {"n": 0}


def _count_write(*a, **k):
    writes["n"] += 1
    return "OK (HTTP 201)"


genesis.extend_to_plant = _count_write
genesis.change_material_view = _count_write
genesis.create_bom = _count_write
genesis.create_routing = _count_write

out = genesis.enable_plant_production("11330", "1010", confirm=False)
data = json.loads(out.split("@@DATA@@", 1)[1]) if "@@DATA@@" in out else {}

a1 = "PREVIEW -- nothing written" in out
a2 = writes["n"] == 0
a3 = data.get("mrp_controller") == "002"                       # grounded = first valid for the plant
a4 = data.get("work_center") == "1010_WC"                      # grounded work center for THIS plant
a5 = len(data.get("components", [])) == 2                      # components resolved from the BOM
steps = " || ".join(data.get("steps", []))
a6 = "production version" in steps and "work center" in steps and "work-scheduling" in steps

# --- grounding TEETH: every ungrounded-plant path ABORTS before any write ---
config_graph.validate_plant_config = lambda plant, **kw: ["MRP controller 'X' is not valid for plant 1010"]
abort_cfg = genesis.enable_plant_production("11330", "1010", confirm=False)
config_graph.validate_plant_config = lambda plant, **kw: []
config_graph.get_relation = lambda rel, plant: {"error": "no RFC / SDK"}
abort_rfc = genesis.enable_plant_production("11330", "1010", confirm=False)
a7 = "ABORTED" in abort_cfg and "not grounded" in abort_cfg
a8 = "ABORTED" in abort_rfc and writes["n"] == 0               # still zero writes across all aborts

print("=== GATE (B6 one-call plant enablement -- PLAN) ===")
print(f"  (1) preview says nothing written              : {a1}")
print(f"  (2) preview performed ZERO writes             : {a2}  (writes={writes['n']})")
print(f"  (3) MRP controller grounded (first valid)     : {a3}  ({data.get('mrp_controller')})")
print(f"  (4) work center grounded for the plant        : {a4}  ({data.get('work_center')})")
print(f"  (5) components resolved from the source BOM   : {a5}")
print(f"  (6) plan lists work-scheduling + routing + PV : {a6}")
print(f"  (7) bad plant config -> ABORT, no write       : {a7}")
print(f"  (8) config read fails -> ABORT, no write      : {a8}")
print(f"\n  ALL PASS: {all([a1, a2, a3, a4, a5, a6, a7, a8])}")
