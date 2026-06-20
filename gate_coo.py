"""GATE -- B5 country-of-origin read-target. The assessor read CountryOfOrigin from the A_Product
HEADER, which is frequently blank even when the value is maintained on the PLANT view (MARC-HERKL) --
so it raised FALSE 'not specified' findings. Probed live (2026-06-16): CoO exists on both the header
and A_ProductPlant; the PIR exposes no origin field here. So the fix reads header -> plant view (NOT
the PIR -- ground, don't guess), without writing any data to satisfy the check.

    uv run python gate_coo.py
"""
import sys, json
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "mcp_server")

import assurance as A

P = A._policies()           # real org policy -- the same standard the board judges against

# --- the PURE check still behaves (sanity) -------------------------------------------
restricted = next(iter(P["country_of_origin"]["restricted_regions"]))   # e.g. RU
f_restricted = A.check_country_of_origin({"Product": "X", "CountryOfOrigin": restricted}, P)
f_blank = A.check_country_of_origin({"Product": "X", "CountryOfOrigin": ""}, P)
a1 = any(f["verdict"] == "fail" and "RESTRICTED" in f["fact"] for f in f_restricted)
a2 = any("not specified" in f["fact"] for f in f_blank)

# --- the FIX: _effective_coo resolves header -> plant view ----------------------------
# mock the plant-view read so the gate is deterministic (no dependence on live master data).
_plant_coo = {"PLANTSET": "DE"}      # this material has CoO maintained at the plant, blank header


def fake_explore(entity, filter="", service="", **kw):
    mat = filter.split("'")[1] if "'" in filter else ""
    return json.dumps({"d": {"results": [{"Product": mat, "Plant": "1010",
                                          "CountryOfOrigin": _plant_coo.get(mat, "")}]}})


A.explore_entity = fake_explore

# (3) header blank, plant view has DE -> resolved from the plant, check PASSES
coo3, src3 = A._effective_coo({"Product": "PLANTSET", "CountryOfOrigin": ""}, "1010")
chk3 = A.check_country_of_origin({"Product": "PLANTSET", "CountryOfOrigin": coo3}, P)
a3 = coo3 == "DE" and "plant" in src3 and all(f["verdict"] == "pass" for f in chk3)

# (4) header blank, plant blank -> genuinely not maintained -> check FAILS (correctly, not a false pass)
coo4, src4 = A._effective_coo({"Product": "NONE", "CountryOfOrigin": ""}, "1010")
chk4 = A.check_country_of_origin({"Product": "NONE", "CountryOfOrigin": coo4}, P)
a4 = coo4 == "" and src4 == "not maintained" and any("not specified" in f["fact"] for f in chk4)

# (5) header set -> header wins, no plant read needed, source reported as 'header'
elevated = (P["country_of_origin"]["elevated_review_regions"] or ["CN"])[0]
coo5, src5 = A._effective_coo({"Product": "HDR", "CountryOfOrigin": elevated}, "1010")
a5 = coo5 == elevated and src5 == "header"

print("=== GATE (B5 country-of-origin read-target) ===")
print(f"  (1) pure check still flags a restricted header CoO          : {a1}")
print(f"  (2) pure check still flags a blank CoO as 'not specified'   : {a2}")
print(f"  (3) blank header + plant-view CoO -> resolved, check PASSES : {a3}  ({coo3} from {src3})")
print(f"  (4) blank everywhere -> 'not maintained', check still FAILS : {a4}")
print(f"  (5) header CoO wins (source=header), no needless plant read : {a5}")
print(f"\n  ALL PASS: {all([a1, a2, a3, a4, a5])}")
