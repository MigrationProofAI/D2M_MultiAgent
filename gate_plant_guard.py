"""GATE -- PLANT-EXTENSION WIRING (Problem B3). The regression: materials born MARA-basic-only (no
plant view) despite the promoted plant-extension capability. Diagnosis: the LOCAL create path bakes the
plant view into the create deep-insert ('born routable'), so the wiring loss sits at two seams --
(1) the CF route's cloud change_material(add), NOT yet live-verified to deep-insert to_Plant, and
(2) an ad-hoc payload built without plant. Neither was guarded, and NO verifier checked the view.

Teeth, all offline/deterministic:
  (a) build_material_payload can no longer silently omit the plant view (plant defaults to SAP_PLANT);
      an EXPLICIT plant='' still builds header-only (caller intent respected).
  (b) the CF create shim reads the material back; when the cloud add dropped the plant view it
      re-issues extend_to_plant (and tolerates 'already exists'); a confirmed view issues NO write.
  (c) the deterministic Verifier flags a basic-view-only material as 'MISSING <mat> plant view' --
      reconciliation now SEES the regression (and the heal loop can extend it).

    uv run python gate_plant_guard.py
"""
import sys, json
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "mcp_server")

# --- (a) the payload builder: plant view always intended unless EXPLICITLY declined ---------------
import sap

built = json.loads(sap.build_material_payload(description="Gate Part", product_type="HAWA",
                                              base_unit="EA", product_group="01"))
f = built["fields"]
pl = ((f.get("to_Plant") or {}).get("results") or [{}])[0].get("Plant")
a1 = pl == (sap.os.getenv("SAP_PLANT", "1710"))                 # defaulted, never silently omitted
built2 = json.loads(sap.build_material_payload(description="Gate Part", product_type="HAWA",
                                               base_unit="EA", product_group="01", plant=""))
a2 = "to_Plant" not in built2["fields"]                         # explicit '' -> header-only respected

# --- (b) the CF create shim: read-back + re-issued extension --------------------------------------
import mcp_route

calls = []
SCRIPT = {}


def _fake_call(server, tool, args, timeout=90.0):
    calls.append((server, tool, args))
    return SCRIPT.get(tool, "")


mcp_route.call = _fake_call
FIELDS = {"Product": "", "ProductType": "HAWA",
          "to_Plant": {"results": [{"Plant": "1710", "MRPType": "PD", "ProcurementType": "F"}]}}

# b-1: cloud add DROPPED the view (read-back shows no Plant) -> extend_to_plant re-issued
calls.clear()
SCRIPT.update({"change_material": "Created. A_Product('12345')",
               "read_material": '{"Product": "12345", "ProductType": "HAWA"}',
               "extend_to_plant": "Extended 12345 to plant 1710 (A_ProductPlant + A_ProductValuation)"})
res = mcp_route.s_create_material(FIELDS, confirm=True)
ext = [c for c in calls if c[1] == "extend_to_plant"]
b1 = len(ext) == 1 and ext[0][2]["material"] == "12345" and ext[0][2]["plant"] == "1710"
b2 = ext and ext[0][2]["mrp_type"] == "PD" and ext[0][2]["confirm"] is True   # PD from the payload, not ND
b3 = '"Product":"12345"' in res and "re-issued via extend_to_plant" in res

# b-2: the view DID land (deep-insert worked) -> zero extra writes
calls.clear()
SCRIPT["read_material"] = '{"Product": "12346", "to_Plant": {"results": [{"Plant": "1710"}]}}'
SCRIPT["change_material"] = "Created. A_Product('12346')"
res2 = mcp_route.s_create_material(FIELDS, confirm=True)
b4 = not [c for c in calls if c[1] == "extend_to_plant"]

# b-3: extend says 'already exists' -> tolerated, reported as present
calls.clear()
SCRIPT["change_material"] = "Created. A_Product('12347')"
SCRIPT["read_material"] = '{"Product": "12347"}'
SCRIPT["extend_to_plant"] = "ERROR: The plant data already exists"
res3 = mcp_route.s_create_material(FIELDS, confirm=True)
b5 = "already-exists" in res3

# b-4: a preview (confirm=false) never triggers the guard
calls.clear()
mcp_route.s_create_material(FIELDS, confirm=False)
b6 = len(calls) == 1 and calls[0][1] == "change_material"

# --- (c) the Verifier SEES a basic-view-only material ----------------------------------------------
import object_verifier

VIEWS = {"11001": [{"Plant": "1710"}], "11002": []}             # 11002 = MARA-basic-only


def _fake_get_material(m, full=False, segments=None, plant=""):
    return json.dumps({"d": {"ProductType": "HAWA", "to_Plant": {"results": VIEWS.get(str(m), [])}}})


object_verifier.get_material = _fake_get_material
object_verifier._pir_ok = lambda m: ("ok", "5300000001")
object_verifier._cost_ok = lambda m: ("ok", "0000000001")

passed, missing, unverified, verdict, vdata = object_verifier.verify_genesis_objects(
    ["11001", "11002"], "1710", expand=False)
c1 = not passed and missing == 1 and "MISSING 11002 plant view" in verdict
rows = {r["mat"]: r for r in vdata["rows"]}
c2 = rows["11001"]["objects"]["plant view"]["status"] == "ok"
c3 = rows["11002"]["objects"]["plant view"]["status"] == "missing"
c4 = "plant" in verdict.splitlines()[3]                          # the report table names the column

# the heal loop's gap summary names the plant-view gap (web._GAP_OBJ) -- checked against the source so
# this gate stays light (importing web pulls fastapi); the regex must classify the new gap kind.
import re as _re
_src = open("web.py", encoding="utf-8").read()
_m = _re.search(r"_GAP_OBJ = re\.compile\(r\"\((.*?)\)\"", _src)
c5 = bool(_m and "plant[- ]?view" in _m.group(1))

print("=== GATE (PLANT-EXTENSION WIRING -- B3) ===")
print(f"  (a1) payload defaults the plant view (SAP_PLANT)     : {a1}  (plant={pl})")
print(f"  (a2) explicit plant='' stays header-only             : {a2}")
print(f"  (b1) CF add dropped view -> extend_to_plant re-issued: {b1}")
print(f"  (b2) re-issue carries the payload's PD, confirm=true : {b2}")
print(f"  (b3) result notes the re-issued extension            : {b3}")
print(f"  (b4) view landed -> NO extra write                   : {b4}")
print(f"  (b5) 'already exists' tolerated as present           : {b5}")
print(f"  (b6) preview never triggers the guard                : {b6}")
print(f"  (c1) verifier flags MISSING plant view               : {c1}")
print(f"  (c2) extended material reads plant-view ok           : {c2}")
print(f"  (c3) basic-only material reads plant-view missing    : {c3}")
print(f"  (c4) report table carries the plant column           : {c4}")
print(f"  (c5) heal-loop gap summary names plant view          : {c5}")
ok = all([a1, a2, b1, b2, b3, b4, b5, b6, c1, c2, c3, c4, c5])
print(f"\n  ALL PASS: {ok}")
sys.exit(0 if ok else 1)
