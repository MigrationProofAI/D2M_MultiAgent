"""GATE — CAD → D2M handoff bridge (Phase 6, the emit_to_plm_erp fulfilment). Proves, offline:
  * preview goes through the full bridge with NO SAP writes and returns the decision card;
  * on commit, the CAD-part# ↔ SAP-material# thread is parsed from the genesis result (FERT via the
    recorded fert_part_number, components via the echoed name) and persisted to the CAD store.

The SAP commit itself is stubbed (a canned run_genesis result) so the gate is deterministic/offline.

    uv run python gate_cad_bridge.py
"""
import sys, json, tempfile, os, shutil
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "mcp_server")

import cad_bridge
from cad_to_genesis import cad_to_genesis

# --- 1) PREVIEW: full bridge, no SAP writes, returns the plan card ---
import sap as _sap
_sap._product_header_fields = lambda: {}            # offline: no $metadata network for passthrough check
prev = cad_bridge.cad_genesis("DSN-0001", confirm=False)
b1 = prev["mode"] == "preview" and prev["fert_part_number"] == "CAD-000001"
b2 = prev["plan_data"]["counts"]["materials"] == 26 and prev["plan_data"]["counts"]["pirs"] == 14
b3 = len(prev["thread_rows"]) == 26

# --- 2) COMMIT (stubbed SAP): thread parsed + persisted ---
# Build a canned genesis result: parent gets a SAP number, each component echoes its CAD name + number.
spec, _thread = cad_to_genesis("DSN-0001")
gres = {"kind": "genesis", "mode": "complete", "plant": "1710",
        "parent": {"description": spec["parent"]["description"], "material": "19000"},
        "components": [{"name": c["name"], "material": str(19001 + i)}
                       for i, c in enumerate(spec["components"])],
        "reconciliation": {"kind": "ReconciliationReport", "planned": 26, "created": 26,
                           "missing": [], "extra": [], "complete": True}}
canned = "GENESIS COMPLETE for 19000 ...\n@@DATA@@" + json.dumps(gres)

# stub the SAP-writing commit path
_tmpstore = tempfile.mkdtemp(prefix="cad_thread_")
os.makedirs(os.path.join(_tmpstore, "cad", "DSN-0001"), exist_ok=True)
import tools as _tools
_orig = _tools.run_genesis_anchored
_tools.run_genesis_anchored = lambda spec, confirm=False, on_step=None: canned
# stub the INDEPENDENT verification (live SAP reads) so the gate stays offline; assert the bridge WIRES
# them and surfaces the independent reconciliation as the completion verdict.
import object_verifier as _ov, conformance as _cf
_ov_orig, _cf_orig = _ov.verify_genesis_objects, _cf.verify_conformance
_ov.verify_genesis_objects = lambda anchor, plant="1710", on_step=None, expand=True: (
    True, 0, 0, "ALL OBJECTS VERIFIED ✓", {"kind": "genesis_verification", "passed": True, "rows": []})
_cf.verify_conformance = lambda spec, anchor, plant="1710", on_step=None: (
    True, [], "CONFORMS ✓", {"kind": "conformance", "diffs": 0, "passed": True, "by_object": {},
                             "reconciliation": {"kind": "ReconciliationReport", "planned": 26, "created": len(anchor),
                                                "missing": [], "extra": [], "complete": True, "verdict": "COMPLETE — zero missing"}})
import cad_bridge as _cb
_real_root = _cb._store_root()
# REDIRECT the thread persist to a TEMP file so the gate NEVER writes/removes the real store's
# DSN-0001/sap_thread.json (an earlier version clobbered the live thread on every gate run).
_tf_path = os.path.join(_tmpstore, "sap_thread.json")
_persist_orig = _cb._persist_thread
def _persist_to_temp(root, did, mapping, fg, plant, intent):
    with open(_tf_path, "w", encoding="utf-8") as f:
        json.dump({"design_id": did, "plant": str(plant), "fg_material": (str(fg) if fg else None),
                   "cad_to_sap": mapping, "count": len(mapping), "document_is_created_by_cad": True}, f)
    return _tf_path
_cb._persist_thread = _persist_to_temp
try:
    res = cad_bridge.cad_genesis("DSN-0001", confirm=True, store_root=_real_root)
finally:
    _tools.run_genesis_anchored = _orig
    _ov.verify_genesis_objects, _cf.verify_conformance = _ov_orig, _cf_orig
    _cb._persist_thread = _persist_orig

m = res["cad_to_sap"]
b4 = res["mode"] == "complete" and res["fg_material"] == "19000"
b5 = m.get("CAD-000001") == "19000"                 # FERT mapped via fert_part_number
b6 = m.get("CAD-000002") == "19001" and len(m) == 26   # every component mapped via echoed name
# the completion verdict comes from the INDEPENDENT reconciliation (conformance), not the maker's own
b7 = (res["complete"] is True and res["reconciliation"]["kind"] == "ReconciliationReport"
      and res["reconciliation"]["planned"] == 26 and res["verification"]["passed"] is True
      and res["conformance"]["passed"] is True)
# thread file persisted (to the TEMP path, not the real store) with mapping + DocumentIsCreatedByCAD
tf = json.load(open(res["thread_file"], encoding="utf-8"))
b8 = (res["thread_file"] == _tf_path and tf["fg_material"] == "19000" and tf["count"] == 26
      and tf["document_is_created_by_cad"] is True)
b9 = tf["cad_to_sap"]["CAD-000021"] == m["CAD-000021"]   # the motor's CAD#↔SAP# persisted
shutil.rmtree(_tmpstore, ignore_errors=True)         # clean ONLY the temp dir; real store untouched

print("=== GATE (CAD → D2M handoff bridge) ===")
print(f"  (1) preview: full bridge, no writes, FERT id     : {b1}")
print(f"  (2) preview: plan counts (26 mat, 14 PIR)        : {b2}")
print(f"  (3) preview: 26 thread rows ready                : {b3}")
print(f"  (4) commit: mode complete, FG 19000              : {b4}")
print(f"  (5) commit: FERT mapped via fert_part_number     : {b5}")
print(f"  (6) commit: all 26 components CAD#→SAP# mapped    : {b6}")
print(f"  (7) commit: INDEPENDENT reconcile+verify+conform : {b7}")
print(f"  (8) thread file persisted (+DocumentIsCreatedByCAD): {b8}")
print(f"  (9) thread file carries each CAD#↔SAP# pair       : {b9}")
ok = all([b1, b2, b3, b4, b5, b6, b7, b8, b9])
print(f"\n  ALL PASS: {ok}")
sys.exit(0 if ok else 1)
