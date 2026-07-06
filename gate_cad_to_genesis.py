"""GATE — CAD → D2M merge adapter (Phase 6). Proves cad_to_genesis turns a released AgentCAD design
into a faithful D2M genesis spec, and that _create_material threads the real SAP classification through.
Fully offline/deterministic against the committed DSN-0001 sample (26-part drill press).

    uv run python gate_cad_to_genesis.py
"""
import sys, json
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "mcp_server")

from cad_to_genesis import cad_to_genesis

spec, thread = cad_to_genesis("DSN-0001")
p = spec["parent"]
comps = spec["components"]
by_name = {c["name"]: c for c in comps}

# --- structure: FLAT, 1 FERT + 25 components, no nesting ---
a1 = p["type"] == "FERT" and p["name"] == "CAD-000001" and p["plant"] == "1710"
a2 = len(comps) == 25 and not any(c.get("components") for c in comps)   # single-level, no sub-assemblies
a3 = "vendor" not in p                                                  # a FERT is made, never sourced

# --- made/bought split follows source MAKE/BUY ---
base = by_name["CAD-000002"]        # base casting — MAKE / HALB
motor = by_name["CAD-000021"]       # AC motor — BUY / HAWA
a4 = base["role"] == "made" and base["type"] == "HALB" and "vendor" not in base
a5 = motor["role"] == "bought" and motor["type"] == "HAWA" and motor["vendor"] == "17300001"
made = [c for c in comps if c["role"] == "made"]
bought = [c for c in comps if c["role"] == "bought"]
a6 = len(made) == 11 and len(bought) == 14                             # matches DSN-0001 type mix

# --- DocumentIsCreatedByCAD=true (literal bool) on EVERY node ---
a7 = (p["attributes"]["DocumentIsCreatedByCAD"] is True
      and all(c["attributes"]["DocumentIsCreatedByCAD"] is True for c in comps))

# --- REAL SAP classification threaded from the part master (not defaults) ---
a8 = base["valuation_class"] == "7900" and base["procurement_type"] == "E"       # HALB
a9 = motor["valuation_class"] == "3100" and motor["procurement_type"] == "F"     # HAWA
a10 = p["valuation_class"] == "7920" and p["procurement_type"] == "E"            # FERT

# --- MaterialGroup (CAD tag) is NOT sent as ProductGroup, but preserved in the thread ---
a11 = all("product_group" not in c for c in comps) and "product_group" not in p
trow = {t["cad_part_number"]: t for t in thread}
a12 = trow["CAD-000002"]["cad_material_group"] == "STR-FE" and trow["CAD-000021"]["cad_material_group"] == "ELE-AL"

# --- quantities come from the eBOM lines (bearings x2, pulley set x2) ---
a13 = by_name["CAD-000015"]["quantity"] == 2 and by_name["CAD-000020"]["quantity"] == 2

# --- digital thread: one row per node (FERT + 25), each with the CAD part number ---
a14 = len(thread) == 26 and all(t["cad_part_number"].startswith("CAD-") for t in thread)

# --- geometry attributes: null in DSN-0001 -> omitted, not sent as blank ---
a15 = all(k not in base["attributes"] for k in ("NetWeight", "MaterialVolume", "SizeOrDimensionText"))

# --- geometry attributes: PRESENT -> mapped to the right SAP header field names ---
from cad_to_genesis import _attributes
mm_geo = {"NetWeight": "3.2", "WeightUnit": "KG", "Volume": "0.0012", "VolumeUnit": "M3",
          "SizeDimensions": "300x300x2mm"}
ga = _attributes(mm_geo)
a16 = (ga["NetWeight"] == "3.2" and ga["MaterialVolume"] == "0.0012"
       and ga["SizeOrDimensionText"] == "300x300x2mm" and ga["DocumentIsCreatedByCAD"] is True)

# --- _create_material THREADS the classification keys through to build_material_payload ---
import genesis as _g
captured = {}
def _fake_bmp(**kw):
    captured.clear(); captured.update(kw)
    return json.dumps({"fields": {"ProductType": kw.get("product_type")}, "extra_notes": []})
_orig_bmp, _orig_cm = _g.build_material_payload, _g.create_material
_g.build_material_payload = _fake_bmp
_g.create_material = lambda fields, confirm=False: 'Created "Product":"19001"'
try:
    _g._create_material({"description": "Base casting", "type": "HALB", "valuation_class": "7900",
                         "procurement_type": "E", "mrp_type": "PD", "unit": "EA"}, "1710")
    a17 = (captured.get("valuation_class") == "7900" and captured.get("procurement_type") == "E"
           and captured.get("mrp_type") == "PD" and captured.get("base_unit") == "EA")
    # backward-compat: a node WITHOUT these keys threads NONE of them (defaults unchanged)
    captured.clear()
    _g._create_material({"description": "Plain part", "type": "HAWA"}, "1710")
    a18 = all(k not in captured for k in ("valuation_class", "procurement_type", "mrp_type", "base_unit"))
finally:
    _g.build_material_payload, _g.create_material = _orig_bmp, _orig_cm

# --- KNOWN-EDGE GUARD: DSN-0001 is flat -> no warning; a synthesized nested eBOM -> flagged, not flattened silently ---
a23 = (spec.get("source") or {}).get("multilevel") is None      # DSN-0001 is single-level -> clean
import tempfile, os as _os, shutil, json as _json
_root = tempfile.mkdtemp(prefix="cad_ml_")
_dd = _os.path.join(_root, "cad", "DSN-ML"); _os.makedirs(_os.path.join(_dd, "part_master"))
_json.dump({"product": {"part_number": "CAD-900", "MaterialType": "FERT", "description": "Nested Rig"},
            "structure": "multi-level eBOM",
            "lines": [{"Component": "CAD-901", "ComponentDescription": "Sub-assembly", "ComponentQuantity": 1}]},
           open(_os.path.join(_dd, "ebom.json"), "w", encoding="utf-8"))
for pn, par in (("CAD-900", None), ("CAD-901", "CAD-900"), ("CAD-902", "CAD-901")):   # CAD-902 nests under CAD-901
    _json.dump({"part_number": pn, "parent": par, "description": pn,
                "material_master": {"MaterialType": "HALB", "ProcurementType": "E"}, "source": "MAKE"},
               open(_os.path.join(_dd, "part_master", pn + ".json"), "w", encoding="utf-8"))
_mlspec, _ = cad_to_genesis("DSN-ML", store_root=_root)
_warn = (_mlspec.get("source") or {}).get("multilevel")
a24 = bool(_warn) and "MULTI-LEVEL" in _warn and "CAD-901" in _warn                  # nested parent surfaced
shutil.rmtree(_root, ignore_errors=True)

# --- plan_report predicts what run_genesis will REALLY write (made/bought by role, not children) ---
# Offline: stub the $metadata read so no network is needed for the passthrough-field check.
import plan_report as _pr
try:
    import sap as _sap
    _sap._product_header_fields = lambda: {}
except Exception:
    pass
_rep = _pr.plan_report(spec, "1710")
c = _rep["data"]["counts"]
a19 = c["materials"] == 26 and c["made"] == 12 and c["bought"] == 14      # 11 HALB + FERT made; 14 HAWA
a20 = c["boms"] == 1 and c["routings"] == 1 and c["prod_versions"] == 1   # only the FERT (flat HALBs have no sub-structure)
a21 = c["pirs"] == 14 and c["costs"] == 0                                 # bought w/ vendor; none have a price
flagtext = " | ".join(f[1] for f in _rep["data"]["flags"])
a22 = "no sub-structure" in flagtext and "not independently producible" in flagtext

print("=== GATE (CAD → D2M merge adapter — DSN-0001) ===")
print(f"  (1)  parent is FERT @ plant 1710                  : {a1}")
print(f"  (2)  flat: 25 components, no nesting              : {a2}")
print(f"  (3)  FERT carries no vendor                       : {a3}")
print(f"  (4)  MAKE part -> made/HALB, no vendor            : {a4}")
print(f"  (5)  BUY part -> bought/HAWA, vendor 17300001     : {a5}")
print(f"  (6)  made/bought split = 11/14 (DSN-0001 mix)     : {a6}")
print(f"  (7)  DocumentIsCreatedByCAD=true on every node    : {a7}")
print(f"  (8)  HALB valuation 7900 / procurement E threaded : {a8}")
print(f"  (9)  HAWA valuation 3100 / procurement F threaded : {a9}")
print(f"  (10) FERT valuation 7920 / procurement E threaded : {a10}")
print(f"  (11) CAD MaterialGroup NOT sent as ProductGroup   : {a11}")
print(f"  (12) CAD MaterialGroup preserved in the thread    : {a12}")
print(f"  (13) quantities from eBOM lines (x2 parts)        : {a13}")
print(f"  (14) digital thread: 26 rows, all CAD part#s      : {a14}")
print(f"  (15) null geometry attrs omitted (not blank)      : {a15}")
print(f"  (16) present geometry -> right SAP header names    : {a16}")
print(f"  (17) _create_material threads classification      : {a17}")
print(f"  (18) no keys -> defaults unchanged (compat)       : {a18}")
print(f"  (19) plan card: 26 mat, 12 made / 14 bought       : {a19}")
print(f"  (20) plan card: 1 BOM/routing/PV (FERT only)      : {a20}")
print(f"  (21) plan card: 14 PIRs, 0 costs (mirrors commit) : {a21}")
print(f"  (22) plan card: honest 'no sub-structure' flag    : {a22}")
print(f"  (23) flat DSN-0001 -> no multilevel warning       : {a23}")
print(f"  (24) nested eBOM DETECTED, not silently flattened : {a24}")
ok = all([a1, a2, a3, a4, a5, a6, a7, a8, a9, a10, a11, a12, a13, a14, a15, a16, a17, a18, a19, a20, a21, a22, a23, a24])
print(f"\n  ALL PASS: {ok}")
sys.exit(0 if ok else 1)
