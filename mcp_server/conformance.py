"""conformance.py -- the CONFORMANCE verifier (a deterministic comparison / recon / audit tool, NO LLM).

Presence verification ("a routing exists") is the floor; real verification is CONFORMANCE: does the ACTUAL
SAP state match the INTENDED contract (the spec), field by field, for every object we created? This reads the
live objects back and diffs them against the spec -- material type + attributes, BOM components + quantities,
routing work centers, PIR vendor + price, cost rate, PV presence -- with a TOLERANT compare (SAP normalises
weights/prices). ~0 LLM tokens, identical every run. It catches what presence can't: e.g. a routing that
exists but fell back to a default work center (the 13 non-conforming routings presence passed on cb2bc730).

Shape, per object:  intent (from spec) -> read actual (from SAP) -> diff -> conforms?  Applies to every
CREATE; the same read-back-and-diff generalises to every CHANGE (stage 2)."""
import re
import json
import concurrent.futures

from sap import get_material                                   # noqa: E402
from make import get_bom, get_routing, read_pir, read_cost_condition   # noqa: E402
from genesis import read_production_version                    # noqa: E402
from object_verifier import _expand_tree                       # truncation-proof: full created set from the tree

_MADE = {"FERT", "HALB"}
_WORKERS = 10


def _data(text):
    m = re.search(r"@@DATA@@(\{.*\})\s*$", text or "", re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}


def _num(x):
    try:
        return round(float(str(x).replace(",", "")), 3)
    except (TypeError, ValueError):
        return None


def _retry(fn, present, tries=3):
    """Call fn up to `tries` times; return the first result that looks PRESENT, else the last. A transient
    empty read must NOT be flagged as a diff/missing -- same retry discipline the presence verifier uses.
    Only re-reads on absence, so a genuinely-absent object still ends up correctly absent after the tries."""
    r = None
    for _ in range(tries):
        r = fn()
        if present(r):
            return r
    return r


def _desc(m):
    """Material description via to_Description (a nav property, not a header field)."""
    try:
        d = json.loads(get_material(str(m), segments=["description"])).get("d", {})
        ds = (d.get("to_Description", {}) or {}).get("results", [])
        return (next((x.get("ProductDescription") for x in ds if x.get("Language") == "EN"), "")
                or (ds[0].get("ProductDescription") if ds else "") or "")
    except Exception:
        return ""


def _descmap(anchor):
    """{description_lower -> matnr} for the created materials, so a spec node maps to its real number."""
    out = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        for m, d in pool.map(lambda x: (str(x), _desc(x)), anchor):
            if d:
                out.setdefault(d.strip().lower(), m)
    return out


def _walk(spec):
    nodes = []

    def rec(n, made_parent):
        made = bool(n.get("components"))
        nodes.append({"node": n, "made": made})
        for c in (n.get("components") or []):
            rec(c, made)
    for c in (spec.get("components") or []):
        rec(c, True)
    # the FERT itself is a made node too
    p = spec.get("parent") or {}
    if p:
        nodes.append({"node": {"name": p.get("description"), "description": p.get("description"),
                               "type": p.get("type", "FERT"), "attributes": p.get("attributes"),
                               "components": spec.get("components"), "routing": spec.get("routing")},
                      "made": True})
    return nodes


def _check_node(entry, plant, descmap):
    """Diff ONE node's created objects against its intended contract. Returns list of findings."""
    n = entry["node"]
    key = str(n.get("description") or n.get("name") or "").strip().lower()
    mat = descmap.get(key)
    if not mat:
        return [{"node": key, "mat": None, "object": "material", "field": "exists",
                 "intended": "created", "actual": "NOT FOUND", "conforms": False}]
    made = entry["made"]
    f = []

    # --- material: type + engineering attributes ---
    def _rd_mat():
        try:
            return json.loads(get_material(str(mat), full=True)).get("d", {})
        except Exception:
            return {}
    d = _retry(_rd_mat, lambda x: bool(x.get("ProductType")))
    it = str(n.get("type") or "").upper()
    at = str(d.get("ProductType") or "").upper()
    f.append({"node": key, "mat": mat, "object": "material", "field": "ProductType",
              "intended": it, "actual": at, "conforms": (it == at)})
    for fld, val in (n.get("attributes") or {}).items():
        # attribute column named as the OData field (case-insensitive); tolerant numeric compare
        real = next((k for k in d if k.lower() == str(fld).lower()), None)
        av = d.get(real) if real else None
        ok = (_num(av) == _num(val)) if _num(val) is not None else (str(av or "").strip() == str(val).strip())
        f.append({"node": key, "mat": mat, "object": "material", "field": str(fld),
                  "intended": val, "actual": av, "conforms": bool(ok)})

    if made:
        # --- BOM: component set + quantities ---
        kids = n.get("components") or []
        intended = {}
        for c in kids:
            cm = descmap.get(str(c.get("description") or c.get("name") or "").strip().lower())
            if cm:
                intended[cm] = _num(c.get("quantity", 1))
        actual = {}
        _bomd = _retry(lambda: _data(get_bom(str(mat), plant)), lambda x: bool(x.get("components")))
        for c in _bomd.get("components", []):
            if c.get("component"):
                actual[str(c["component"])] = _num(c.get("quantity", 1))
        bom_ok = (set(intended) == set(actual)) and all(intended[k] == actual.get(k) for k in intended)
        f.append({"node": key, "mat": mat, "object": "BOM", "field": "components+qty",
                  "intended": f"{len(intended)} comp", "actual": f"{len(actual)} comp",
                  "conforms": bool(bom_ok),
                  "detail": None if bom_ok else {"missing": sorted(set(intended) - set(actual)),
                                                 "extra": sorted(set(actual) - set(intended))}})
        # --- routing: work-center sequence ---
        ops = n.get("routing") or [{"work_center": "ASSEMBLY"}, {"work_center": "PACK01"}]
        intended_wc = [o.get("work_center") for o in ops]
        _rtd = _retry(lambda: _data(get_routing(str(mat), plant)), lambda x: bool(x.get("operations")))
        actual_wc = [o.get("work_center") for o in _rtd.get("operations", [])]
        f.append({"node": key, "mat": mat, "object": "routing", "field": "work_centers",
                  "intended": " > ".join(w for w in intended_wc if w),
                  "actual": " > ".join(w for w in actual_wc if w),
                  "conforms": (intended_wc == actual_wc)})
        # --- production version: presence (binding is genesis policy, not spec-declared) ---
        def _rd_pv():                                  # read_production_version returns PLAIN JSON (no @@DATA@@)
            try:
                return json.loads(read_production_version(str(mat), plant) or "{}")
            except Exception:
                return {}
        pv = _retry(_rd_pv, lambda x: bool(x.get("versions")))
        has_pv = bool(pv.get("versions"))
        f.append({"node": key, "mat": mat, "object": "production version", "field": "exists",
                  "intended": "0001", "actual": (pv.get("versions") or ["NONE"])[0], "conforms": has_pv})
    else:
        # --- PIR: vendor + net price ---
        pir = _retry(lambda: _data(read_pir(str(mat))), lambda x: bool(x.get("supplier") or x.get("price")))
        iv, ip = str(n.get("vendor") or ""), _num(n.get("price"))
        av, ap = str(pir.get("supplier") or ""), _num(pir.get("price"))
        f.append({"node": key, "mat": mat, "object": "PIR", "field": "supplier",
                  "intended": iv, "actual": av, "conforms": (iv == av) if iv else True})
        if ip is not None:
            f.append({"node": key, "mat": mat, "object": "PIR", "field": "net_price",
                      "intended": ip, "actual": ap, "conforms": (ip == ap)})
        # --- cost condition: rate ---
        cost = _retry(lambda: _data(read_cost_condition(str(mat))), lambda x: x.get("price") is not None)
        ar = _num(cost.get("price"))
        if ip is not None:
            f.append({"node": key, "mat": mat, "object": "cost", "field": "rate",
                      "intended": ip, "actual": ar, "conforms": (ip == ar)})
    return f


def verify_conformance(spec, anchor, plant="1710", on_step=None):
    """Audit the created objects against the intended contract. Returns (passed, findings, report, data)."""
    def emit(msg):
        if on_step:
            try:
                on_step({"kind": "reasoning", "text": msg})
            except Exception:
                pass

    anchor = [str(a) for a in (anchor or [])]
    n0 = len(anchor)
    anchor = _expand_tree(anchor, plant)              # widen a truncated anchor to the FULL created tree
    if len(anchor) != n0:
        emit(f"scope widened via BOM tree: {n0} → {len(anchor)} materials (truncation-proof)")
    emit(f"conformance audit: mapping {len(anchor)} created materials…")
    descmap = _descmap(anchor)
    nodes = _walk(spec)
    emit(f"diffing {len(nodes)} nodes against the intended contract…")
    findings = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        for res in pool.map(lambda e: _check_node(e, plant, descmap), nodes):
            findings.extend(res)
    checked = len(findings)
    diffs = [x for x in findings if not x["conforms"]]
    passed = not diffs
    by_obj = {}
    for x in findings:
        o = x["object"]
        by_obj.setdefault(o, [0, 0])
        by_obj[o][0] += 1
        if not x["conforms"]:
            by_obj[o][1] += 1

    lines = [f"CONFORMANCE AUDIT (actual SAP state vs intended contract) — {len(nodes)} nodes, {checked} field checks",
             "  " + " · ".join(f"{o}: {t - d}/{t} conform" + (f" ({d} DIFF)" if d else "") for o, (t, d) in by_obj.items())]
    if diffs:
        lines.append(f"\nNON-CONFORMING ({len(diffs)}):")
        for x in diffs[:40]:
            lines.append(f"  {x['mat'] or '—'} {x['object']}.{x['field']}: intended [{x['intended']}] "
                         f"≠ actual [{x['actual']}]")
        if len(diffs) > 40:
            lines.append(f"  … +{len(diffs) - 40} more")
    lines.append("\nVERDICT: " + ("CONFORMS — SAP state matches the approved plan ✓"
                                  if passed else f"{len(diffs)} field(s) DO NOT conform to the plan"))
    data = {"kind": "conformance", "plant": plant, "nodes": len(nodes), "checks": checked,
            "diffs": len(diffs), "passed": passed, "by_object": by_obj, "findings": findings}
    return passed, diffs, "\n".join(lines), data


def reconcile_routings(spec, anchor, plant="1710", on_step=None):
    """PRE-vs-POST routing reconciliation (a focused recon/audit tool). For every MADE node: the PLANNED work
    centers (from the spec's Operations) vs the ACTUAL routing group + work centers read from SAP -- MATCH /
    DRIFT / MISSING per node. Deterministic, ~0 tokens. Returns {passed, report, data}."""
    def emit(msg):
        if on_step:
            try:
                on_step({"kind": "reasoning", "text": msg})
            except Exception:
                pass

    anchor = _expand_tree([str(a) for a in (anchor or [])], plant)
    emit(f"routing recon: mapping {len(anchor)} materials, diffing planned vs actual…")
    descmap = _descmap(anchor)
    made = [e for e in _walk(spec) if e["made"]]

    def _one(entry):
        n = entry["node"]
        key = str(n.get("description") or n.get("name") or "").strip().lower()
        mat = descmap.get(key)
        ops = n.get("routing") or [{"work_center": "ASSEMBLY"}, {"work_center": "PACK01"}]
        planned = [o.get("work_center") for o in ops]
        if not mat:
            return {"node": key, "mat": None, "planned": planned, "group": None, "actual": [], "status": "NO-MATERIAL"}
        rt = _retry(lambda: _data(get_routing(str(mat), plant)), lambda x: bool(x.get("operations")))
        actual = [o.get("work_center") for o in rt.get("operations", [])]
        status = "MATCH" if planned == actual else ("MISSING" if not actual else "DRIFT")
        return {"node": key, "mat": mat, "planned": planned, "group": rt.get("number"),
                "actual": actual, "status": status}

    with concurrent.futures.ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        rows = list(pool.map(_one, made))
    rows.sort(key=lambda r: int(r["mat"]) if r["mat"] and str(r["mat"]).isdigit() else 0)
    match = sum(1 for r in rows if r["status"] == "MATCH")
    drift = [r for r in rows if r["status"] == "DRIFT"]
    missing = [r for r in rows if r["status"] in ("MISSING", "NO-MATERIAL")]
    plan_wcs = sorted({w for r in rows for w in r["planned"] if w})
    act_wcs = sorted({w for r in rows for w in r["actual"] if w})
    passed = not drift and not missing

    lines = [f"ROUTING RECONCILIATION (planned vs actual) — {len(rows)} made nodes",
             f"  MATCH {match} · DRIFT {len(drift)} · MISSING {len(missing)}",
             f"  work centers: planned {len(plan_wcs)} → created {len(act_wcs)}"
             f"  · planned-not-created {sorted(set(plan_wcs) - set(act_wcs)) or 'none'}"]
    if drift:
        lines.append("DRIFT (actual routing ≠ planned work centers):")
        for r in drift[:30]:
            lines.append(f"  {r['mat']} {r['node'][:30]:<30} planned [{' > '.join(r['planned'])}] "
                         f"≠ actual [{' > '.join(r['actual'])}] (group {r['group']})")
    lines.append("VERDICT: " + ("ALL ROUTINGS MATCH THE PLAN ✓" if passed
                                else f"{len(drift)} drift + {len(missing)} missing"))
    data = {"kind": "routing_recon", "plant": plant, "made": len(rows), "match": match,
            "drift": len(drift), "missing": len(missing), "planned_wcs": plan_wcs,
            "actual_wcs": act_wcs, "not_created": sorted(set(plan_wcs) - set(act_wcs)), "rows": rows}
    return {"passed": passed, "report": "\n".join(lines), "data": data}
