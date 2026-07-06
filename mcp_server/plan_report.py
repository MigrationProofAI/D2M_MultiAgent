"""plan_report.py -- the PRE-GENESIS structured report (the typed 'Genesis Plan Contract').

A human is asked to approve a genesis, but a rollup of counts (or a truncated tree) is nothing to sign off on.
This produces a DETERMINISTIC, decision-grade report from the parsed spec + live $metadata: what every object
type will be written across its KEY VIEWS, the VALUE for each field, and the PROVENANCE of that value (did it
come from the file, a derived rule, a genesis default, or a $metadata-validated passthrough?). Same spec ->
identical report, ~0 LLM tokens. The board then judges THIS, not a truncated dump.

Structure: header (scope + rolled-up cost) · a CONTRACT per object type/view (field -> value/rule -> source)
· cost-by-system + anomaly FLAGS · per-instance drill-down (in the data payload). No SAP writes; pure read."""
import os
import json
import statistics


def _routing_invalid_wcs(plant):
    """Work centers NOT valid for production routings (SAP task-list type N -> CR/084), from work_centers.json.
    Lets the plan FLAG a routing on such a work center BEFORE commit -- the create would 400 and heal would
    silently fall back to a default (the drift the conformance audit catches post-hoc)."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "work_centers.json")) as fh:
            wcs = json.load(fh)
        return {w["work_center"] for w in wcs.get(str(plant), []) if w.get("routing_valid") is False}
    except Exception:
        return set()

try:
    from sap import _product_header_fields          # live $metadata: valid A_Product header fields
except Exception:
    def _product_header_fields():
        return {}

_MADE = {"FERT", "HALB"}
_VCLASS = {"ROH": "3000", "HAWA": "3100", "FERT": "7920", "HALB": "7900"}   # genesis defaults by type


def _walk(spec):
    """Flatten the spec tree into instances with depth + rolled-up multiplier (qty through the parents)."""
    out = []

    def rec(n, depth, mult, top):
        q = float(n.get("quantity", 1) or 1)
        m = mult * q
        # made/bought mirrors run_genesis: it keys PIR/cost on ROLE, not on having children. So a flat
        # made node (a CAD HALB with no sub-parts) is MADE (no PIR), not bought. Fall back to
        # children-presence only when the spec node carries no explicit role (older specs).
        role = str(n.get("role") or "").lower()
        made = (role == "made") if role in ("made", "bought") else bool(n.get("components"))
        out.append({"node": n, "depth": depth, "mult": m, "made": made,
                    "sub": made and bool(n.get("components")),   # a made SUB-ASSEMBLY: own BOM/routing/PV
                    "system": top or n.get("name")})
        for c in (n.get("components") or []):
            rec(c, depth + 1, m, top or n.get("name"))
    for c in (spec.get("components") or []):
        rec(c, 1, 1.0, c.get("name"))
    return out


def _material_contract(has_attrs):
    """The FIELD CONTRACT for a material, by key view: (view, field, value-or-rule, provenance).
    Mirrors how genesis actually builds via build_material_payload -- so it's what WILL be written."""
    c = [
        ("Basic Data", "ProductType", "<row type>", "file:type"),
        ("Basic Data", "ProductDescription", "<row description> (≤40)", "file:description"),
        ("Basic Data", "BaseUnit", "<row unit, else EA>", "file:unit / default"),
        ("Basic Data", "ProductGroup", "01 (neutral) or a mapped code", "file:part_master else default 01"),
        ("Basic Data", "IndustrySector", "M", "default:genesis"),
        ("Plant / MRP", "MRPType", "PD", "file:planning else default"),
        ("Plant / MRP", "ProcurementType", "E/F", "file:part_master else derived:role"),
        ("Plant / MRP", "MRPResponsible", "001", "default:genesis"),
        ("Plant / MRP", "AvailabilityCheckType", "02", "default:genesis"),
        ("Plant / MRP", "LotSizingProcedure", "EX", "default:genesis"),
        ("Plant / MRP", "PlannedDeliveryDurationInDays", "10", "default:genesis"),
        ("Valuation", "ValuationClass", "by type (ROH 3000 / HAWA 3100 / HALB 7900 / FERT 7920)", "file:part_master else derived:type"),
        ("Valuation", "StandardPrice", "100.00", "default:genesis"),
        ("Valuation", "Currency", "USD", "default:genesis"),
        ("Sales (FERT only)", "SalesOrg / DistrChannel", "1710 / 10", "default:genesis"),
        ("Sales (FERT only)", "ItemCategoryGroup", "NORM", "default:genesis"),
        ("Sales (FERT only)", "Tax classification", "complete DE/US set", "default:genesis"),
    ]
    if has_attrs:
        c.append(("Basic Data (passthrough)", "<any OData field named in the BOM>",
                  "<row value>", "metadata:validated"))
    return c


_PIR_CONTRACT = [
    ("Purchasing", "Supplier", "<row vendor>", "file:vendor"),
    ("Purchasing", "PurchasingOrganization", "<plant>", "derived:plant"),
    ("Purchasing", "NetPriceAmount", "<row price>", "file:price"),
    ("Purchasing", "Currency", "USD", "default:genesis"),
    ("Purchasing", "MaterialPlannedDeliveryDurationInDays", "10", "default:genesis"),
    ("Purchasing", "MinimumOrderQuantity", "1", "default:genesis"),
]
_COST_CONTRACT = [
    ("Condition", "ConditionType", "PPR0", "default:genesis"),
    ("Condition", "ConditionRateAmount", "<row price>", "file:price"),
    ("Condition", "Currency", "USD", "default:genesis"),
    ("Condition", "Supplier", "<row vendor>", "file:vendor"),
]
_BOM_CONTRACT = [
    ("Header", "Material (parent)", "<made node>", "file:structure"),
    ("Header", "BillOfMaterialVariantUsage", "1", "default:genesis"),
    ("Header", "Alternative", "01", "default:genesis"),
    ("Items", "Component + Quantity", "<row children + qty>", "file:structure"),
]
_ROUTING_CONTRACT = [
    ("Header", "Group / Counter", "<assigned by SAP>", "derived:SAP"),
    ("Operation", "OperationNumber", "<Operations rows, else 10/20>", "file:operations / default"),
    ("Operation", "WorkCenter", "<Operations row>", "file:operations"),
    ("Operation", "SetupTime / RunTime", "<Operations row, else 10 / 5>", "file:operations / default"),
]
_PV_CONTRACT = [
    ("Version", "ProductionVersion", "0001", "default:genesis"),
    ("Version", "BOM binding", "alt 01 / usage 1", "default:genesis"),
    ("Version", "Lot size", "1 - 10000", "default:genesis"),
    ("Version", "Validity", "today .. 31.12.9999", "default:genesis"),
]


def _flags(inst, spec):
    """Deterministic anomaly scan -- the concrete risks a human should weigh before committing."""
    bought = [i for i in inst if not i["made"]]
    made = [i for i in inst if i["made"]]
    flags = []
    vendors = {(i["node"].get("vendor")) for i in bought if i["node"].get("vendor")}
    if bought and len(vendors) == 1:
        flags.append(("warn", f"Single-source risk — ALL {len(bought)} bought parts on one vendor "
                              f"{sorted(vendors)[0]}"))
    elif bought and len(vendors) <= max(2, len(bought) // 20):
        flags.append(("warn", f"Concentrated sourcing — {len(bought)} bought parts on only {len(vendors)} vendors"))
    np = [i for i in bought if i["node"].get("price") in (None, "")]
    nv = [i for i in bought if not i["node"].get("vendor")]
    if np:
        flags.append(("warn", f"{len(np)} bought part(s) with NO price → cost condition will default"))
    if nv:
        flags.append(("bad", f"{len(nv)} bought part(s) with NO vendor → no PIR/cost will be created"))
    # A made SUB-ASSEMBLY (has children) with no explicit routing gets D2M's default operations.
    subs_no_rt = [i for i in made if i.get("sub") and not i["node"].get("routing")]
    if subs_no_rt:
        flags.append(("info", f"{len(subs_no_rt)} made sub-assembly(ies) have no explicit routing → default Assembly+Packaging"))
    # A flat made LEAF (made in-house but no sub-parts, e.g. a single-level CAD HALB) is created as a
    # material in the parent BOM but gets NO BOM/routing/production version of its own -- so it is not
    # independently producible until decomposed. This is honest to surface before commit.
    made_leaf = [i for i in made if not i.get("sub")]
    if made_leaf:
        flags.append(("info", f"{len(made_leaf)} made component(s) have no sub-structure → created as "
                              f"semi-finished in the BOM, but not independently producible (no own BOM/routing/PV)"))
    prices = [float(i["node"]["price"]) for i in bought if i["node"].get("price") not in (None, "")]
    if len(prices) >= 8:
        med = statistics.median(prices)
        out = [i for i in bought if i["node"].get("price") and float(i["node"]["price"]) > 12 * med]
        if out:
            flags.append(("info", f"{len(out)} price outlier(s) > 12× median (${med:.2f}) — e.g. "
                                  + ", ".join(i["node"]["name"] for i in out[:3])))
    descs = [str(i["node"].get("description") or i["node"].get("name")).lower() for i in inst]
    dups = sorted({d for d in descs if descs.count(d) > 1})
    if dups:
        flags.append(("info", f"{len(dups)} duplicate description(s) → possible unintended reuse "
                              + ", ".join(dups[:3])))
    attrs = sum(1 for i in inst if i["node"].get("attributes"))
    if attrs == 0:
        flags.append(("info", "0 materials carry engineering attributes (weight / dimensions / origin)"))
    else:
        flags.append(("ok", f"{attrs} material(s) carry engineering attributes (validated passthrough)"))
    if not flags:
        flags.append(("ok", "No anomalies detected"))
    return flags


def plan_report(spec, plant="1710"):
    """Deterministic pre-genesis report. Returns {summary, data} -- summary is readable (chat + board),
    data is the structured contract/rollup/flags/instances (drives the card, holds the drill-down)."""
    inst = _walk(spec)
    made = [i for i in inst if i["made"]]
    bought = [i for i in inst if not i["made"]]
    subs = [i for i in inst if i["sub"]]                    # made sub-assemblies (own BOM/routing/PV)
    has_parent = bool((spec.get("parent") or {}).get("description") or (spec.get("parent") or {}).get("material"))
    depth = max((i["depth"] for i in inst), default=0)
    total = sum(float(i["node"]["price"]) * i["mult"]
                for i in bought if i["node"].get("price") not in (None, ""))
    by_system = {}
    for i in bought:
        if i["node"].get("price") not in (None, ""):
            by_system[i["system"]] = by_system.get(i["system"], 0.0) + float(i["node"]["price"]) * i["mult"]
    fert = spec.get("parent", {})
    has_attrs = any(i["node"].get("attributes") for i in inst)
    flags = _flags(inst, spec)

    # Structure objects (BOM + routing + production version) are created for the FERT parent and for
    # each MADE SUB-ASSEMBLY (a made node with its own children) -- NOT for a flat childless made node.
    # PIR/cost are created only for a bought part that actually carries a vendor/price. This mirrors
    # run_genesis exactly, so the card predicts what the commit will really write.
    n_struct = len(subs) + (1 if has_parent else 0)
    counts = {"materials": len(inst) + (1 if has_parent else 0),
              "made": len(made) + (1 if has_parent else 0), "bought": len(bought), "depth": depth,
              "boms": n_struct, "routings": n_struct, "prod_versions": n_struct,
              "pirs": sum(1 for i in bought if i["node"].get("vendor")),
              "costs": sum(1 for i in bought if i["node"].get("price") not in (None, ""))}
    contract = {
        "Materials": _material_contract(has_attrs),
        "Purchase Info Records": _PIR_CONTRACT,
        "Cost Conditions": _COST_CONTRACT,
        "Bills of Material": _BOM_CONTRACT,
        "Routings": _ROUTING_CONTRACT,
        "Production Versions": _PV_CONTRACT,
    }
    # per-instance content for each TAB (so every tab shows real rows, not just the contract template)
    materials = [{"name": i["node"].get("name"), "type": i["node"].get("type"),
                  "role": "made" if i["made"] else "bought",
                  "vendor": i["node"].get("vendor"), "price": i["node"].get("price"),
                  "attrs": i["node"].get("attributes") or {}, "depth": i["depth"], "system": i["system"]}
                 for i in inst]
    pirs = [{"part": i["node"].get("name"), "vendor": i["node"].get("vendor"),
             "price": i["node"].get("price"), "system": i["system"]}
            for i in bought if i["node"].get("vendor")]
    costs = [{"part": i["node"].get("name"), "rate": i["node"].get("price"),
              "condition": "PPR0", "vendor": i["node"].get("vendor")}
             for i in bought if i["node"].get("price") not in (None, "")]
    # BOM/routing/PV rows: the FERT parent (its components are the top-level list) + each made
    # sub-assembly. A flat made node (no children) gets NO structure row -- matching the commit.
    _struct_src = ([{"node": spec.get("parent") or {}, "components": spec.get("components") or [],
                     "routing": spec.get("routing")}] if has_parent else []) + \
                  [{"node": i["node"], "components": i["node"].get("components") or [],
                    "routing": i["node"].get("routing")} for i in subs]
    boms = [{"parent": s["node"].get("name") or s["node"].get("description"),
             "type": s["node"].get("type", "FERT"), "usage": "1", "alt": "01",
             "components": [{"name": c.get("name"), "qty": c.get("quantity", 1)} for c in s["components"]]}
            for s in _struct_src]
    routings = [{"node": s["node"].get("name") or s["node"].get("description"),
                 "operations": [{"op": o.get("operation"), "wc": o.get("work_center"), "text": o.get("text")}
                                for o in (s["routing"] or [])] or
                                [{"op": "10", "wc": "ASSEMBLY", "text": "Final Assembly (default)"},
                                 {"op": "20", "wc": "PACK01", "text": "Packaging (default)"}]}
                for s in _struct_src]
    pvs = [{"node": s["node"].get("name") or s["node"].get("description"), "version": "0001",
            "binding": "alt 01 / usage 1", "lot": "1-10000"} for s in _struct_src]
    work_centers = sorted({o["wc"] for r in routings for o in r["operations"] if o.get("wc")})
    # PRE-COMMIT work-center validity: flag routings planned on work centers not valid for task-list type N.
    _bad_wc = _routing_invalid_wcs(plant)
    _bad_used = sorted(set(work_centers) & _bad_wc)
    if _bad_used:
        _bad_nodes = [r["node"] for r in routings if any(o.get("wc") in _bad_wc for o in r["operations"])]
        flags.insert(0, ("bad", f"{len(_bad_nodes)} routing(s) planned on work centers NOT valid for routings "
                                f"(SAP task-list type N / CR-084): {_bad_used} — these WILL fail at commit and "
                                f"fall back to a default. Fix the Operations before committing."))

    data = {"kind": "genesis_plan", "plant": plant,
            "fert": {"description": fert.get("description"), "type": fert.get("type", "FERT"),
                     "attrs": fert.get("attributes") or {}},
            "counts": counts, "total_cost": round(total, 2),
            "cost_by_system": {k: round(v, 2) for k, v in sorted(by_system.items(), key=lambda x: -x[1])},
            "contract": contract, "flags": flags, "materials": materials,
            "pirs": pirs, "costs": costs, "boms": boms, "routings": routings, "pvs": pvs,
            "work_centers": work_centers}

    # readable summary (chat + what the board reasons on -- the WHOLE plan, not a truncated tree)
    L = [f"GENESIS PLAN — {fert.get('description')} @ {plant}  (deterministic pre-genesis report)",
         f"Scope: {counts['materials']} materials · {counts['made']} made / {counts['bought']} bought · {depth} levels",
         f"Objects: {counts['boms']} BOMs · {counts['routings']} routings · {counts['prod_versions']} production "
         f"versions · {counts['pirs']} PIRs · {counts['costs']} cost conditions",
         f"Purchased-parts cost (rolled up): ${total:,.2f}",
         "Cost by system: " + " · ".join(f"{k} ${v:,.0f}" for k, v in list(data['cost_by_system'].items())[:6]),
         "",
         "FIELD CONTRACT (what will be written, and where each value comes from):"]
    for obj, rows in contract.items():
        L.append(f"  {obj}:")
        seen = set()
        for view, field, val, prov in rows:
            tag = f"[{prov}]"
            L.append(f"    {view:<24} {field:<26} = {val}   {tag}")
    L.append("")
    L.append("FLAGS:")
    for lvl, msg in flags:
        L.append(f"  {'⚠' if lvl in ('warn', 'bad') else ('✓' if lvl == 'ok' else '·')} {msg}")
    return {"summary": "\n".join(L), "data": data}
