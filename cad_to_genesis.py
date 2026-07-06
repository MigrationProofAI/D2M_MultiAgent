"""cad_to_genesis.py — the CAD → D2M merge adapter (Phase 6, "the agent IS the integration layer").

AgentCAD (the Studio track, cadplm/) emits, per RELEASED design, a SAP-shaped store:
    <store>/cad/<design_id>/ebom.json                 # product{FERT} + single-level lines[]
    <store>/cad/<design_id>/part_master/CAD-*.json    # one per part incl. the FERT; material_master{}
    <store>/plm/<PLM>/part_spec/PLM-*.json            # planning{MRPType,…} + cad_part_number link
Its `emit_to_plm_erp` was always a documented STUB — "where you'd POST each line to SAP." **D2M genesis
IS that POST.** This adapter turns one released design into a D2M genesis spec run_genesis can build.

SCOPE — KNOWN EDGE (do not treat as a silent assumption): CAD→genesis is proven FLAT. Every eBOM in the
cadplm_store samples is single-level (1 FERT + N components, all parented to the FERT), so the adapter
emits a flat spec. Multi-level eBOM handoff (a nested sub-assembly whose parent is another component —
the pump-skid / 320-part explosion the Ideate2Design2Make2Plan thesis targets) is UNBUILT. This is not
assumed away: `cad_to_genesis` DETECTS a non-flat input (any part parented to something other than the
FERT) and returns a `multilevel` warning in spec["source"] rather than silently flattening it — so the
day AgentCAD emits nested assemblies, the handoff surfaces the gap instead of quietly dropping structure.

What it maps (grounded against cadplm/sap_shape.py + the real DSN-0001..0016 samples):
  * FLAT by construction — every AgentCAD eBOM is single-level (1 FERT + N components, no nesting), so
    the spec is a flat parent + components list (no sub-assembly recursion, no CAD routing → D2M's
    placeholder routing on the FERT). A multi-level input is flagged, not flattened silently (see above).
  * MaterialType (FERT/HALB/HAWA), ProcurementType (E/F), ValuationClass (7900/3100/…) are REAL SAP
    values → pass straight through (valuation/procurement via the threaded classification keys, since
    they are plant/valuation VIEW fields the header attribute-passthrough can't reach).
  * MaterialGroup ("STR-FE", "ELE-AL") is a SYNTHESIZED CAD tag, NOT a valid SAP ProductGroup (T023)
    code — so it is NOT sent as ProductGroup (that would risk a create rejection). It defaults to D2M's
    honest "01" placeholder and is preserved in the thread/provenance. Populate _MGRP_MAP once the
    landscape's valid ProductGroup codes are known to turn this back on.
  * Geometry attributes (weight/volume/size) ride D2M's type-aware metadata passthrough as A_Product
    header fields — carried when present, omitted when null (they are `_basis`-estimated / usually null
    until real STEP geometry lands; conformance then faithfully reflects estimate-vs-actual).
  * DocumentIsCreatedByCAD=true on EVERY part — the literal digital-thread marker (a real boolean).
  * Bought (HAWA) parts carry no vendor/price in CAD → default vendor 17300001, price omitted (honest;
    D2M sources the PIR at its default, or a later enrich/web-source pass fills it).

Returns (spec, thread): `spec` for run_genesis; `thread` is the CAD side of the digital thread — one
row per node {cad_part_number, description, type, role, cad_material_group} — so once genesis returns
the created SAP material numbers, the caller persists CAD-part# ↔ SAP-material# (matched by description,
which both sides truncate to 40 chars — see conformance._normdesc).
"""
import os
import json
from pathlib import Path

_DEF_PLANT = os.getenv("SAP_PLANT", "1710")
_DEF_VENDOR = os.getenv("SAP_DEFAULT_VENDOR", "17300001")

# CAD-internal MaterialGroup tag -> a VALID SAP ProductGroup code. EMPTY by default: until the
# landscape's real T023 codes are known, every part falls back to D2M's neutral "01" (honest
# "unclassified") rather than shipping an invalid group that SAP would reject at create. Add entries
# like {"STR-FE": "<valid code>"} to turn real ProductGroup passthrough on.
_MGRP_MAP: dict = {}

# CAD material_master attribute -> the exact A_Product HEADER OData field name D2M's passthrough wants.
# Only these header-resident fields flow (view fields go via the threaded classification keys, below).
# A wrong/absent name is silently skipped-with-a-note by the passthrough, never an error.
_ATTR_MAP = {
    "NetWeight": "NetWeight",
    "GrossWeight": "GrossWeight",
    "WeightUnit": "WeightUnit",
    "Volume": "MaterialVolume",          # CAD 'Volume' -> S/4 header 'MaterialVolume'
    "VolumeUnit": "VolumeUnit",
    "SizeDimensions": "SizeOrDimensionText",
}


def _store_root(store_root=None) -> Path:
    """Resolve the CAD store root: explicit arg, else $CAD_STORE_ROOT, else the sibling
    AgentCAD/cadplm_store (dev), else a d2m/ S3-hydrated mirror if one was pulled locally."""
    for cand in (store_root, os.getenv("CAD_STORE_ROOT"),
                 Path(__file__).resolve().parent.parent / "AgentCAD" / "cadplm_store"):
        if cand and Path(cand).exists():
            return Path(cand)
    raise FileNotFoundError(
        "CAD store not found. Pass store_root=..., set CAD_STORE_ROOT, or place AgentCAD/cadplm_store "
        "beside the D2M repo (the shared S3 seam is d2m/cad/, d2m/plm/).")


def _load_design(design_id: str, root: Path):
    """(ebom dict, {part_number: part_master dict}) for one released design."""
    d = root / "cad" / design_id
    ebom = json.loads((d / "ebom.json").read_text(encoding="utf-8"))
    masters = {}
    pm_dir = d / "part_master"
    for p in sorted(pm_dir.glob("*.json")):
        m = json.loads(p.read_text(encoding="utf-8"))
        masters[str(m.get("part_number"))] = m
    return ebom, masters


def _attributes(mm: dict) -> dict:
    """CAD material_master -> D2M metadata-passthrough attributes (header fields only, non-null),
    always including the DocumentIsCreatedByCAD digital-thread marker."""
    attrs = {"DocumentIsCreatedByCAD": True}
    for cad_key, sap_field in _ATTR_MAP.items():
        v = mm.get(cad_key)
        if v not in (None, "", "None"):
            attrs[sap_field] = v
    return attrs


def _node(part_number: str, description: str, mm: dict, role: str, quantity, thread: list) -> dict:
    """Build ONE D2M component/parent node from a CAD part master, and record its thread row."""
    ptype = str(mm.get("MaterialType") or ("HAWA" if role == "bought" else "HALB"))
    node = {
        "name": part_number,                                   # CAD part# -> traceable in the report
        "description": str(description or part_number),
        "type": ptype,
        "role": role,
        "quantity": quantity if quantity not in (None, "") else 1,
        "unit": str(mm.get("BaseUnit") or "EA"),
        "attributes": _attributes(mm),
    }
    # REAL SAP classification (view fields) threaded straight from the part master.
    if mm.get("ValuationClass"):
        node["valuation_class"] = str(mm["ValuationClass"])
    if mm.get("ProcurementType"):
        node["procurement_type"] = str(mm["ProcurementType"])
    # MaterialGroup: map to a valid SAP ProductGroup if known, else leave to D2M's "01" default.
    cad_group = mm.get("MaterialGroup")
    mapped = _MGRP_MAP.get(str(cad_group)) if cad_group else None
    if mapped:
        node["product_group"] = mapped
    if role == "bought":
        node["vendor"] = _DEF_VENDOR                           # CAD carries no vendor/price
    thread.append({"cad_part_number": part_number, "description": node["description"],
                   "type": ptype, "role": role, "cad_material_group": cad_group})
    return node


def cad_to_genesis(design_id: str, store_root=None, plant: str = None):
    """Turn one RELEASED AgentCAD design into (D2M genesis spec, digital-thread rows).

    spec  -> run_genesis(spec, confirm=...) (flat: parent FERT + components).
    thread -> [{cad_part_number, description, type, role, cad_material_group}] to bind CAD#↔SAP# once
              genesis returns the created material numbers.
    """
    root = _store_root(store_root)
    plant = plant or _DEF_PLANT
    ebom, masters = _load_design(design_id, root)

    product = ebom.get("product") or {}
    fert_pn = str(product.get("part_number") or "")
    fert_mm = (masters.get(fert_pn) or {}).get("material_master") or {}
    thread: list = []

    # KNOWN-EDGE GUARD: the adapter emits a FLAT spec. If a part is parented to something other than the
    # FERT (a real multi-level eBOM), surface it — never silently flatten away sub-assembly structure.
    nested = sorted({str(m.get("parent")) for m in masters.values()
                     if m.get("parent") not in (None, "", fert_pn)})
    multilevel = None
    if nested or str(ebom.get("structure") or "").strip().lower() not in ("single-level ebom", ""):
        multilevel = (f"MULTI-LEVEL eBOM detected (structure={ebom.get('structure')!r}, "
                      f"{len(nested)} non-FERT parent(s): {nested[:5]}). The adapter FLATTENS to one BOM "
                      f"level — nested sub-assembly BOMs/routings are NOT emitted. Multi-level handoff is unbuilt.")

    parent = _node(fert_pn, product.get("description"), fert_mm, "made", 1, thread)
    parent["type"] = str(product.get("MaterialType") or fert_mm.get("MaterialType") or "FERT")
    parent["plant"] = plant
    parent.pop("vendor", None)                                 # a FERT is made, never sourced

    components = []
    for line in ebom.get("lines") or []:
        cpn = str(line.get("Component") or "")
        pm = masters.get(cpn) or {}
        mm = pm.get("material_master") or {}
        role = "bought" if str(pm.get("source") or mm.get("ProcurementType")).upper() in ("BUY", "F") else "made"
        desc = line.get("ComponentDescription") or pm.get("description") or cpn
        qty = line.get("ComponentQuantity", pm.get("qty", 1))
        components.append(_node(cpn, desc, mm, role, qty, thread))

    spec = {"parent": parent, "components": components,
            "source": {"kind": "agentcad", "design_id": design_id,
                       "intent": ebom.get("intent"), "fert_part_number": fert_pn,
                       "structure": ebom.get("structure"), "multilevel": multilevel}}
    return spec, thread


if __name__ == "__main__":                                     # quick manual peek: python cad_to_genesis.py DSN-0001
    import sys
    did = sys.argv[1] if len(sys.argv) > 1 else "DSN-0001"
    spec, thread = cad_to_genesis(did)
    print(json.dumps({"parent": spec["parent"], "n_components": len(spec["components"]),
                      "first_component": spec["components"][0], "thread_rows": len(thread)},
                     indent=2, ensure_ascii=False))
