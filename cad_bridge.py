"""cad_bridge.py — the CAD → D2M handoff (Phase 6, work items 2-4). Fulfils AgentCAD's documented
`emit_to_plm_erp` STUB: on a released design, build the genesis spec (cad_to_genesis), run D2M genesis
(the real SAP POST the stub deferred), and persist the CAD-part# ↔ SAP-material# DIGITAL THREAD.

The thread falls out for free: cad_to_genesis sets each node's `name` to its CAD part number, and
run_genesis echoes that `name` alongside the SAP `material` it minted — so parsing the genesis result
yields {CAD-000002: 19001, …} with no extra SAP reads. The FERT is mapped via the spec's recorded
fert_part_number (run_genesis reports the parent by description, not name).

Two entry shapes (the brief's "in-process import OR an HTTP call"):
  * cad_genesis(design_id, confirm=…) — in-process; AgentCAD's flow.approve() can import and call this.
  * POST /api/cad/genesis (web.py) — the decoupled seam; AgentCAD's Flask posts a design_id, D2M owns
    the write chain + verification. Same core.

confirm=False previews (the board's decision card, no SAP writes). confirm=True commits: materials +
BOM + routing + PV + PIR/cost, anchored + reconciled by D2M's deterministic + conformance gates
(actual SAP vs the CAD-intended spec, field by field — the CAD digital thread is now conformance-checked).
"""
import os
import re
import sys
import json
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "mcp_server"))

from cad_to_genesis import cad_to_genesis, _store_root

_DATA = "@@DATA@@"


def _parse_gres(text: str) -> dict:
    m = re.search(r"@@DATA@@(\{.*\})\s*$", str(text or ""), re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}


def _thread_map(spec: dict, gres: dict) -> dict:
    """{CAD part number -> SAP material number} from the genesis result. Components carry their CAD
    part# in `name` (set by the adapter); the FERT is mapped via spec.source.fert_part_number."""
    mapping = {}
    fert_pn = ((spec.get("source") or {}).get("fert_part_number"))
    pmat = (gres.get("parent") or {}).get("material")
    if fert_pn and pmat:
        mapping[str(fert_pn)] = str(pmat)

    def _add(c):
        if c.get("name") and c.get("material"):
            mapping[str(c["name"])] = str(c["material"])
        for ch in c.get("children") or []:
            _add(ch)
    for c in gres.get("components") or []:
        _add(c)
    return mapping


def _persist_thread(store_root: Path, design_id: str, mapping: dict, fg_material, plant, intent) -> str:
    """Write the digital thread back into the CAD store (the shared S3 seam) so AgentCAD's registry /
    lineage can show the real SAP material numbers. cad/<design_id>/sap_thread.json."""
    out = store_root / "cad" / design_id / "sap_thread.json"
    payload = {"design_id": design_id, "plant": str(plant), "fg_material": (str(fg_material) if fg_material else None),
               "intent": intent, "cad_to_sap": mapping, "count": len(mapping),
               "document_is_created_by_cad": True}
    try:
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return str(out)


def cad_genesis(design_id: str, confirm: bool = False, plant: str = None,
                store_root=None, on_step=None) -> dict:
    """Release-to-SAP handoff for ONE AgentCAD design. Returns a structured result:
    {design_id, mode, fg_material, cad_to_sap{…}, thread_rows, plan|report, thread_file}.

    confirm=False -> a decision-grade plan (no writes). confirm=True -> commit + anchor + the CAD#↔SAP#
    thread, persisted to the CAD store."""
    root = _store_root(store_root)
    plant = plant or os.getenv("SAP_PLANT", "1710")
    spec, thread = cad_to_genesis(design_id, store_root=root, plant=plant)

    _src = spec.get("source") or {}
    if not confirm:
        # PREVIEW: the board's decision card, deterministic, no SAP master-data writes.
        from plan_report import plan_report
        pr = plan_report(spec, plant)
        return {"design_id": design_id, "mode": "preview", "plant": plant,
                "fert_part_number": _src.get("fert_part_number"),
                "multilevel_warning": _src.get("multilevel"),   # non-null iff a nested eBOM was flattened
                "thread_rows": thread, "plan_summary": pr["summary"], "plan_data": pr["data"]}

    # COMMIT: the real POST the AgentCAD stub deferred.
    from tools import run_genesis_anchored
    result_text = run_genesis_anchored(spec, confirm=True, on_step=on_step)
    gres = _parse_gres(result_text)
    mapping = _thread_map(spec, gres)
    fg_material = (gres.get("parent") or {}).get("material")
    thread_file = _persist_thread(root, design_id, mapping, fg_material, plant, _src.get("intent"))

    # INDEPENDENT VERIFICATION — the CAD commit rides the SAME verified-completion net as the chat
    # genesis path (which runs this in web.py's verify block). The endpoint bypasses that WS handler, so
    # we invoke it here explicitly: no committed write may go through an UNVERIFIED path. The Verifier
    # re-reads EVERY created object against the CAD-intended spec, field by field. Best-effort: a read
    # hiccup must not lose the created materials/thread, so it degrades to a note, never a raise.
    created = sorted(set(mapping.values()), key=lambda x: int(x) if str(x).isdigit() else 0)
    verification = reconciliation = conformance = None
    try:
        from object_verifier import verify_genesis_objects
        from conformance import verify_conformance
        vpassed, vmissing, vunver, vverdict, vdata = verify_genesis_objects(created, plant, on_step=on_step)
        verification = {"passed": bool(vpassed), "missing": vmissing, "unverified": vunver,
                        "verdict": vverdict, "data": vdata}
        cpassed, cdiffs, crep, cdata = verify_conformance(spec, created, plant, on_step=on_step)
        reconciliation = cdata.get("reconciliation")          # planned/created/missing/extra/verdict
        conformance = {"passed": bool(cpassed), "diffs": cdata.get("diffs"), "report": crep,
                       "by_object": cdata.get("by_object")}
    except Exception as e:
        verification = verification or {"error": f"{type(e).__name__}: {e}"}

    # the sole completion verdict: the INDEPENDENT manifest reconciliation (not the maker's own).
    complete = bool((reconciliation or {}).get("complete")) if reconciliation else None
    return {"design_id": design_id, "mode": "complete", "plant": plant,
            "fg_material": (str(fg_material) if fg_material else None),
            "cad_to_sap": mapping, "thread_rows": thread, "thread_file": thread_file,
            "complete": complete,                              # None if verification could not run
            "reconciliation": reconciliation or gres.get("reconciliation"),   # independent; maker's as fallback
            "maker_reconciliation": gres.get("reconciliation"), "incomplete": gres.get("incomplete"),
            "verification": verification, "conformance": conformance,
            "report": result_text.split(_DATA, 1)[0].rstrip()}


if __name__ == "__main__":                                     # python cad_bridge.py DSN-0001 [--commit]
    did = sys.argv[1] if len(sys.argv) > 1 else "DSN-0001"
    commit = "--commit" in sys.argv
    res = cad_genesis(did, confirm=commit)
    if res["mode"] == "preview":
        print(res["plan_summary"][:1500])
        print(f"\n[{len(res['thread_rows'])} thread rows ready; run with --commit to POST to SAP]")
    else:
        print(f"FG {res['fg_material']} · {len(res['cad_to_sap'])} CAD↔SAP mappings · thread → {res['thread_file']}")
        for k, v in list(res["cad_to_sap"].items())[:5]:
            print(f"  {k} → {v}")
