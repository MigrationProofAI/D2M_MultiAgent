"""GATE -- B1 coded-field grounding enforcement. The codebook-grounding skill ADVISES; this proves the
DETERMINISTIC backstop: a write whose coded fields aren't grounded -- an invalid codebook value, a
missing required field, or a plant-specific value wrong for the plant -- is BLOCKED before it reaches
SAP (so it can't bounce back as a cryptic reject). Severity/active comes from policies.json.

    uv run python gate_grounding.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import grounding as g


def _first_valid(field, fallback):
    s = g._valid_codes(field)
    return sorted(s)[0] if s else fallback


pt_set = g._valid_codes("ProductType") or set()
bu_set = g._valid_codes("BaseUnit") or set()
good_pt = "HAWA" if "HAWA" in pt_set else _first_valid("ProductType", "ROH")
good_bu = "EA" if "EA" in bu_set else _first_valid("BaseUnit", "ST")
good_pg = _first_valid("ProductGroup", "50101001")

# (1) invalid coded value -> blocked
b_code = g.validate_grounding({"ProductType": "ZZZ", "BaseUnit": good_bu, "ProductGroup": good_pg}, require=True)
# (2) missing required field (no BaseUnit) -> blocked
b_miss = g.validate_grounding({"ProductType": good_pt, "ProductGroup": good_pg}, require=True)
# (3) wrong-plant storage location (171A is 1710's, not 1010's) -> blocked (nested deep-insert shape)
b_sloc = g.validate_grounding({
    "ProductType": good_pt, "BaseUnit": good_bu, "ProductGroup": good_pg,
    "to_Plant": {"results": [{"Plant": "1010",
        "to_StorageLocation": {"results": [{"Plant": "1010", "StorageLocation": "171A"}]}}]}}, require=True)
# (4) fully grounded -> passes
ok = g.validate_grounding({"ProductType": good_pt, "BaseUnit": good_bu, "ProductGroup": good_pg}, require=True)
# (5) enforce() respects the policy: a block string for bad, None for good
e_bad = g.enforce({"ProductType": "ZZZ", "BaseUnit": good_bu, "ProductGroup": good_pg}, require=True)
e_ok = g.enforce({"ProductType": good_pt, "BaseUnit": good_bu, "ProductGroup": good_pg}, require=True)

a1 = any("ProductType='ZZZ'" in x for x in b_code)
a2 = any("BaseUnit" in x and "missing" in x for x in b_miss)
a3 = any("171A" in x for x in b_sloc)
a4 = ok == []
a5 = bool(e_bad) and (e_ok is None)

# (6/7) REGRESSION: when config-graph can't read the plant config (no pyrfc/SDK -- codebook_extract
# raises SystemExit, a BaseException), grounding must DEGRADE: never crash, never false-block the
# plant-specific value. This is the exact bug that crashed a live genesis create in the rig's .venv.
import config_graph as _cg
_orig = _cg._read_relation
_cg._CACHE.clear()
def _boom(rel, plant):
    raise SystemExit("pyrfc not installed")          # exactly what codebook_extract raises
_cg._read_relation = _boom
try:
    norfc = g.validate_grounding({"ProductType": good_pt, "BaseUnit": good_bu, "ProductGroup": good_pg,
        "to_Plant": {"results": [{"Plant": "1010",
            "to_StorageLocation": {"results": [{"Plant": "1010", "StorageLocation": "171A"}]}}]}}, require=True)
    rel = _cg.get_relation("storage_location", "1010")    # must RETURN {"error"}, not raise
    crashed = False
except BaseException:
    norfc, rel, crashed = None, None, True
finally:
    _cg._read_relation = _orig
    _cg._CACHE.clear()
a6 = (not crashed) and isinstance(rel, dict) and "error" in rel          # config-graph degrades, doesn't crash
a7 = (norfc is not None) and not any("171A" in x for x in norfc)         # unreadable -> NOT false-blocked

print("=== GATE (good codes used: ProductType={}, BaseUnit={}, ProductGroup={}) ===".format(good_pt, good_bu, good_pg))
print(f"  (1) invalid coded value (ProductType=ZZZ) BLOCKED        : {a1}")
print(f"  (2) missing required field (BaseUnit) BLOCKED            : {a2}")
print(f"  (3) wrong-plant storage location (171A@1010) BLOCKED     : {a3}")
print(f"  (4) fully grounded payload PASSES                        : {a4}")
print(f"  (5) enforce() blocks bad / passes good (policy-driven)   : {a5}")
print(f"  (6) no RFC/SDK -> config-graph degrades (no crash)       : {a6}")
print(f"  (7) no RFC/SDK -> plant-specific NOT false-blocked       : {a7}")
print(f"\n  ALL PASS: {all([a1, a2, a3, a4, a5, a6, a7])}")
