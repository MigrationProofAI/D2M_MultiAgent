"""GATE -- the config-relationship-graph (B2). Plant-specific values the value codebook CANNOT hold
(storage locations, MRP controllers) are read from SAP config (T001L / T024D), cached per plant, and
a value that is not valid FOR THAT PLANT is BLOCKED before it reaches SAP. This closes the exact gap
the live 1010 extension hit: storage location couldn't be grounded, MRP controller was guessed/omitted
and SAP rejected the plant view.

    uv run python gate_config_graph.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import config_graph as cg

PLANT = "1010"
sloc = cg.get_relation("storage_location", PLANT).get("values", [])
ctrl = cg.get_relation("mrp_controller", PLANT).get("values", [])
good_sloc = "101A"
good_ctrl = next((v["code"] for v in ctrl), None)

print(f"=== config graph for plant {PLANT} ===")
print(f"  storage locations: {len(sloc)}  e.g. {[v['code'] for v in sloc][:5]}")
print(f"  MRP controllers  : {len(ctrl)}  e.g. {[v['code'] for v in ctrl][:5]}")

block_bad_sloc = cg.validate_plant_config(PLANT, storage_location="171A")              # 1710's sloc
block_no_ctrl = cg.validate_plant_config(PLANT, mrp_type="PD", mrp_controller=None)     # planning, no controller
block_bad_ctrl = cg.validate_plant_config(PLANT, mrp_controller="ZZZ")                  # not a real controller
pass_good = cg.validate_plant_config(PLANT, storage_location=good_sloc, mrp_type="PD", mrp_controller=good_ctrl)
pass_nd = cg.validate_plant_config(PLANT, mrp_type="ND")                                # no-planning -> no controller needed

a1 = len(sloc) > 0 and any(v["code"] == "101A" for v in sloc)
a2 = len(ctrl) > 0
a3 = bool(block_bad_sloc)
a4 = bool(block_no_ctrl)
a5 = bool(block_bad_ctrl)
a6 = pass_good == []
a7 = pass_nd == []
a8 = ("storage_location", PLANT) in cg._CACHE and ("mrp_controller", PLANT) in cg._CACHE

print("\n=== GATE ===")
print(f"  (1) storage locations read for the plant (incl 101A)      : {a1}")
print(f"  (2) MRP controllers read for the plant                    : {a2}")
print(f"  (3) wrong-plant storage location (171A@1010) BLOCKED      : {a3}")
print(f"       -> {block_bad_sloc[0] if block_bad_sloc else ''}"[:96])
print(f"  (4) planning MRP type (PD) with NO controller BLOCKED     : {a4}")
print(f"  (5) invalid MRP controller (ZZZ) BLOCKED                  : {a5}")
print(f"  (6) valid config (101A + real controller + PD) PASSES     : {a6}")
print(f"  (7) no-planning type (ND) needs no controller             : {a7}")
print(f"  (8) read CACHED per plant (no per-material RFC)            : {a8}")
print(f"\n  ALL PASS: {all([a1, a2, a3, a4, a5, a6, a7, a8])}")
