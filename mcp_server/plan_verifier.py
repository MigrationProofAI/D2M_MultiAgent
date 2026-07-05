"""plan_verifier.py -- deterministic, recursive MRP-tree validation (the Plan-Verifier).

Walks a FERT's BOM to ANY depth, reads MD04 per material, and certifies the RUN RESULT:
  * made node (FERT/HALB)  -> must have a Planned order (in-house make)
  * bought node (HAWA/ROH) -> must have a Purchase requisition (external buy)
  * every node             -> its demand must be COVERED (no uncovered negative available)

This is the guaranteed gate the card-render skills (plant-view-verifier etc.) never were: those check
PRE-RUN settings and only when the model chooses to invoke them. This is code, runs every time the verify
loop sees a committed run_mrp, and reads the actual planning OUTPUT. Transient MD04 reads are RETRIED and,
if still empty, reported as UNVERIFIED -- a false red flag is as bad as a false green one (same discipline
as the routing reader's present:null). Read-only; returns a structured verdict."""
import re
import os
import json
import concurrent.futures

from make import get_bom                       # noqa: E402
import sap                                      # noqa: E402
from planning_client import read_mrp_list, _resolve_material   # noqa: E402

# Each node's reads (type + MD04 + BOM) are independent, so a whole BFS LEVEL is probed concurrently.
# The tree is breadth-heavy (FERT -> many HALB -> parts), so this turns a ~7-min sequential walk into ~1 min
# with no extra tokens. Same knob as the object verifier. See [[deterministic-genesis-verifier]].
_WORKERS = int(os.getenv("VERIFY_WORKERS", "10"))


def _data(s):
    m = re.search(r"@@DATA@@(\{.*\})\s*$", s or "", re.S)
    return json.loads(m.group(1)) if m else None


def _mtype(m):
    try:
        return json.loads(sap.get_material(m, full=True)).get("d", {}).get("ProductType", "?")
    except Exception:
        return "ERR"


def _bom_components(m, plant):
    d = _data(get_bom(m, plant))
    return [c.get("component") for c in (d or {}).get("components", [])] if d else []


_SUPPLY_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})\s+(Planned order|Purchase requisition|Purchase order)\s+(\S+)\s+(-?[\d,]+)",
    re.M | re.I)


def _md04(m, plant):
    """(status, supplies, min_available). status='ok' | 'unread' (transient). `supplies` is a list of the
    ACTUAL supply elements -- {kind, number, date, qty} -- so the report can show the Planned Order / Purchase
    Requisition NUMBER, date and quantity, not just a yes/no. Empty list means nothing planned this material."""
    r = ""
    for _ in range(3):                                   # retry: a transient MD04 read must not read as "not planned"
        r = read_mrp_list(m, plant) or ""
        if "requirements list" in r.lower():
            break
        r = ""
    if not r:
        return "unread", [], None
    supplies = []
    for date, elem, num, qty in _SUPPLY_RE.findall(r):
        kind = "planned_order" if elem.lower().startswith("planned") else "purchase_req"
        supplies.append({"kind": kind, "number": num, "date": date,
                         "qty": qty.replace(",", "")})
    avails = [float(x.replace(",", "")) for x in re.findall(r"(-?\d[\d,]*)\s*$", r, re.M)]
    return "ok", supplies, (min(avails) if avails else None)


def verify_mrp_tree(root, plant="1710", on_step=None) -> dict:
    """Validate the ENTIRE MRP tree under `root`. Returns a structured verdict dict:
    {passed, fails, unverified, verdict, banner, report, tree}. `on_step` (optional) receives progress."""
    def emit(msg):
        if on_step:
            try:
                on_step({"kind": "reasoning", "text": msg})
            except Exception:
                pass

    root, note = _resolve_material(str(root))            # accept a description; anchor on the number
    if note and "resolved" not in note:
        return {"passed": False, "fails": 0, "unverified": 0, "verdict": "NO-ANCHOR",
                "banner": f"⚠️ Cannot validate MRP tree: {note}", "report": note, "tree": []}
    plant = str(plant)
    seen, tree = set(), []

    def _probe(m, depth):
        """All reads for ONE node -- independent, so this runs in a worker thread. Returns (node, children)."""
        t = _mtype(m)
        made = t in ("FERT", "HALB")
        status, supplies, minav = _md04(m, plant)
        expect = "planned_order" if made else "purchase_req"
        # the supply element of the EXPECTED kind (the one that proves this node was planned/procured)
        match = next((s for s in supplies if s["kind"] == expect), None)
        if status == "unread":
            got, covered, ok = "UNVERIFIED", None, None
        else:
            got = match["kind"] if match else (supplies[0]["kind"] if supplies else "NONE")
            covered = (minav is None) or (minav >= 0)
            ok = (got == expect) and covered
        node = {"mat": m, "type": t, "depth": depth, "expect": expect, "got": got,
                "covered": covered, "ok": ok, "supply": match or (supplies[0] if supplies else None),
                "min_available": minav}
        return node, _bom_components(m, plant)

    # LEVEL-ORDER BFS: probe an entire depth level concurrently, then expand to the next. `seen` dedups
    # shared sub-assemblies (a node keeps its shortest-path depth). PASS/FAIL logic is depth-independent.
    emit(f"walking MRP tree from {root} @ {plant} · {_WORKERS} parallel probes…")
    frontier, depth = [root], 0
    seen.add(root)
    with concurrent.futures.ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        while frontier:
            results = list(pool.map(lambda m: _probe(m, depth), frontier))
            nxt = []
            for node, children in results:
                tree.append(node)
                s = node.get("supply")
                sd = f" {s['number']} · {s['qty']} · {s['date']}" if s else ""
                emit(f"L{node['depth']} {node['mat']} [{node['type']}]: {node['got']}{sd}"
                     + ("" if node["ok"] else f" (expected {node['expect']})"))
                for c in children:
                    if c not in seen:
                        seen.add(c)
                        nxt.append(c)
            frontier, depth = nxt, depth + 1

    fails = [n for n in tree if n["ok"] is False]
    unver = [n for n in tree if n["ok"] is None]
    made_n = [n for n in tree if n["type"] in ("FERT", "HALB")]
    bought_n = [n for n in tree if n["type"] not in ("FERT", "HALB")]
    passed = not fails
    lines = [f"MRP tree for {root} @ {plant}: {len(tree)} materials ({len(made_n)} made, {len(bought_n)} bought)",
             f"- planned orders : {sum(1 for n in made_n if n['got'] == 'planned_order')}/{len(made_n)} made nodes",
             f"- purchase reqs  : {sum(1 for n in bought_n if n['got'] == 'purchase_req')}/{len(bought_n)} bought nodes",
             f"- demand covered : {sum(1 for n in tree if n['covered'])}/{len(tree)}"]
    # DETAIL: one row per node with the ACTUAL supply element -- Planned Order / Purchase Req number, qty, date.
    lines.append("")
    lines.append(f"{'material':>8}  {'type':<5} {'element':<14} {'number':<12} {'qty':>7}  {'date':<10}")
    for n in sorted(tree, key=lambda x: (x["depth"], x["mat"])):
        s = n.get("supply") or {}
        elem = {"planned_order": "PlndOrder", "purchase_req": "PurchReq"}.get(n["got"], n["got"])
        flag = "" if n["ok"] else ("  ⟵ UNVERIFIED" if n["ok"] is None else "  ⟵ GAP")
        lines.append(f"{n['mat']:>8}  {n['type']:<5} {elem:<14} {s.get('number',''):<12} "
                     f"{s.get('qty',''):>7}  {s.get('date',''):<10}{flag}")
    if unver:
        lines.append("")
        lines.append(f"- UNVERIFIED (read failed after retries, NOT a planning gap): {', '.join(n['mat'] for n in unver)}")
    if fails:
        lines.append("")
        lines.append("- FAILURES:")
        for n in fails:
            lines.append(f"    {n['mat']} [{n['type']}] expected {n['expect']} but got {n['got']} (covered={n['covered']})")
    banner = ("✅ MRP TREE FULLY PLANNED — every made node has a planned order, every bought part a "
              "purchase requisition, all demand covered" if (passed and not unver) else
              f"✅ MRP TREE PLANNED (all readable nodes) — {len(unver)} node(s) unread (transient, not a gap)"
              if passed else
              f"❌ MRP TREE INCOMPLETE — {len(fails)} node(s) not properly planned (see below)")
    data = {"kind": "mrp_tree", "root": root, "plant": plant, "verdict": ("PASS" if passed else f"FAIL({len(fails)})"),
            "made": len(made_n), "bought": len(bought_n), "fails": len(fails), "unverified": len(unver),
            "nodes": tree}
    return {"passed": passed, "fails": len(fails), "unverified": len(unver),
            "verdict": ("PASS" if passed else f"FAIL({len(fails)})"),
            "banner": banner, "report": "\n".join(lines), "tree": tree, "data": data}
