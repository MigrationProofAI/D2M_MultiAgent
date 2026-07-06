"""object_verifier.py -- DETERMINISTIC genesis verification (the object-level Verifier).

Walks the CREATED materials and reads each object back in Python (NO LLM), certifying everything a
genesis should have produced:
  * material exists with the right type
  * made (FERT/HALB) -> a BOM + a routing + a production version
  * bought (HAWA/ROH) -> a PIR + a cost condition

Returns (passed, missing, unverified, verdict_text) -- the SAME shape as orchestrate.verify_claim, so it
drops straight into web.py's verify/heal loop. But because the reading + classifying happen in code, it
costs ~0 LLM tokens and has NO context limit -- it lands at 6 materials or 6,000, where the LLM verifier
crashed past ~120 (the 255k overflow on bom_150). A transient read is RETRIED and, if still unreadable,
classified UNVERIFIED -- never a false MISSING (a false red flag is as bad as a false green one)."""
import re
import os
import json
import concurrent.futures

from sap import get_material                         # noqa: E402
from make import get_bom, read_pir, read_cost_condition   # noqa: E402
from genesis import read_routing, read_production_version  # noqa: E402

# Per-material checks are INDEPENDENT reads -> run them concurrently so a big tree verifies in ~1 min
# instead of ~10 (150 materials x ~5 sequential CF reads). Still per-material MCP-contract calls, just
# in parallel. Tunable; kept modest so we don't hammer the CF read servers.
_WORKERS = int(os.getenv("VERIFY_WORKERS", "10"))


def _mtype(m):
    try:
        return json.loads(get_material(m, full=True)).get("d", {}).get("ProductType")
    except Exception:
        return None


def _head_and_plant(m, plant):
    """(ProductType, plant_view_status) in ONE read: header + to_Plant $expanded, filtered to `plant`.
    B3: a created material MUST carry its plant view ('born routable') -- a MARA-basic-only material is
    a real gap the presence verifier previously could not see (the plant-extension regression). Status:
    'ok' (a to_Plant row for this plant) | 'missing' (expand read fine, no row) | 'unread' (transient)."""
    for _ in range(3):
        try:
            d = json.loads(get_material(m, segments=["plant"], plant=plant)).get("d", {})
        except Exception:
            continue
        t = d.get("ProductType")
        if not t:
            continue
        pv = d.get("to_Plant")
        if isinstance(pv, dict) and isinstance(pv.get("results"), list):
            return t, ("ok" if pv["results"] else "missing")
        return t, "unread"
    return None, "unread"


def _bom_children(m, plant):
    """Component material numbers of m's BOM (from get_bom's @@DATA@@ payload), or [] if none/unreadable."""
    try:
        r = get_bom(m, plant) or ""
        mm = re.search(r"@@DATA@@(\{.*\})\s*$", r, re.S)
        if not mm:
            return []
        return [str(c.get("component")) for c in json.loads(mm.group(1)).get("components", []) if c.get("component")]
    except Exception:
        return []


def _expand_tree(roots, plant):
    """Enumerate the FULL material set by walking the BOM tree from `roots` (parallel BFS). This is the
    TRUNCATION-PROOF anchor: the genesis result text is capped at 8000 chars (agent.py), so mining it for
    material numbers silently drops everything past the cut -> the verifier would certify a SUBSET and call
    it complete (a false green). Walking the actual BOM can't miss a node no matter how big the tree."""
    seen = set(str(r) for r in roots)
    frontier = list(seen)
    with concurrent.futures.ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        while frontier:
            nxt = []
            for kids in pool.map(lambda m: _bom_children(m, plant), frontier):
                for c in kids:
                    if c not in seen:
                        seen.add(c)
                        nxt.append(c)
            frontier = nxt
    return sorted(seen, key=lambda x: int(x) if str(x).isdigit() else 0)


def _dnum(text, *keys):
    """Pull a field from a read's trailing @@DATA@@ json payload (BOM / PIR / cost carry one)."""
    mm = re.search(r"@@DATA@@(\{.*\})\s*$", text or "", re.S)
    if not mm:
        return None
    try:
        d = json.loads(mm.group(1))
        for k in keys:
            if d.get(k) not in (None, ""):
                return d.get(k)
    except Exception:
        pass
    return None


# Each helper returns (status, detail) -- status in 'ok'|'missing'|'unread', detail the ACTUAL identifier
# (BOM number, routing group, PV version, PIR number, cost-condition number) so the report can name every
# object it certified, not just count them. Retries a transient/empty read before declaring missing.
def _bom_ok(m, plant):
    for _ in range(3):
        r = get_bom(m, plant) or ""
        low = r.lower()
        if "component(s)" in low and "no bom" not in low:
            num = _dnum(r, "number") or (re.search(r"BOM\s+(\w+)\s+for", r) or [None, None])[1]
            return "ok", num
        if "no bom found" in low:
            return "missing", None
    return "unread", None


def _routing_ok(m, plant):
    for _ in range(3):
        try:
            d = json.loads(read_routing(m, plant) or "{}")
        except Exception:
            continue
        if d.get("present") is True:
            rs = d.get("routings") or []
            return "ok", (rs[0].get("group") if rs else None)
        if d.get("present") is False:
            return "missing", None
    return "unread", None


def _pv_ok(m, plant):
    for _ in range(3):
        try:
            d = json.loads(read_production_version(m, plant) or "{}")
        except Exception:
            continue
        if d.get("versions"):
            return "ok", ",".join(str(v) for v in d["versions"])
        if d.get("versions") == []:
            return "missing", None
    return "unread", None


def _pir_ok(m):
    for _ in range(3):
        r = read_pir(m) or ""
        low = r.lower()
        if "info record" in low and "no purchase" not in low:
            return "ok", _dnum(r, "number")
        if "no purchase info" in low or "no info record" in low:
            return "missing", None
    return "unread", None


def _cost_ok(m):
    for _ in range(3):
        r = read_cost_condition(m) or ""
        low = r.lower()
        if re.search(r"\d+\.\d+", r) and "no " not in low[:24] and "not found" not in low:
            return "ok", _dnum(r, "number")
        if "no cost" in low or "not found" in low or "no condition" in low:
            return "missing", None
    return "unread", None


def _check_material(m, plant):
    """Certify ONE material's objects. Pure read, no shared state -> safe to run in a worker thread.
    Returns (mat, type_or_None, [missing...], [unverified...], detail) where detail names each object's id.
    EVERY material is also checked for its PLANT VIEW (B3): basic-view-only = MISSING, heal-able via
    extend_to_plant -- the same read that confirms the type, so no extra call."""
    t, pview = _head_and_plant(m, plant)
    if not t:
        return m, None, [f"{m} material"], [], {}   # could not confirm the material exists at all
    miss, unv, detail = [], [], {}
    checks = [("plant view", (pview, plant if pview == "ok" else None))]
    if t in ("FERT", "HALB"):
        checks += [("BOM", _bom_ok(m, plant)), ("routing", _routing_ok(m, plant)),
                   ("production version", _pv_ok(m, plant))]
    else:
        checks += [("PIR", _pir_ok(m)), ("cost condition", _cost_ok(m))]
    for obj, (st, ident) in checks:
        detail[obj] = {"status": st, "id": ident}
        if st == "missing":
            miss.append(f"{m} {obj}")
        elif st == "unread":
            unv.append(f"{m} {obj}")
    return m, t, miss, unv, detail


def verify_genesis_objects(anchor, plant="1710", on_step=None, expand=True):
    """Certify every object for the anchored materials. Returns (passed, missing, unverified, verdict).

    Per-material checks are independent reads, so they run CONCURRENTLY (VERIFY_WORKERS threads): a 150-tree
    lands in ~1 min instead of ~10, still one MCP-contract read per object -- just not one-at-a-time.

    expand=True (default) first walks the BOM tree from the anchor so the scope is the COMPLETE material set,
    not whatever survived the 8000-char truncation of the genesis result text -- otherwise the verifier would
    certify a subset and call it complete (a false green at scale). Pass expand=False if the caller already
    holds the authoritative full set."""
    def emit(msg):
        if on_step:
            try:
                on_step({"kind": "reasoning", "text": msg})
            except Exception:
                pass

    anchor = [str(a) for a in (anchor or [])]
    if not anchor:
        return True, 0, 0, "No created materials in scope -- nothing to verify.", {"kind": "genesis_verification", "rows": []}
    if expand:
        n0 = len(anchor)
        anchor = _expand_tree(anchor, plant)
        if len(anchor) != n0:
            emit(f"scope widened via BOM tree: {n0} anchored → {len(anchor)} total (truncation-proof)")
    missing, unverified, rows = [], [], []
    made_n = bought_n = confirmed_mats = 0
    emit(f"deterministic verify: {len(anchor)} materials · {_WORKERS} parallel readers…")
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        futs = {pool.submit(_check_material, m, plant): m for m in anchor}
        for fut in concurrent.futures.as_completed(futs):
            m, t, miss, unv, detail = fut.result()
            missing.extend(miss)
            unverified.extend(unv)
            if t:
                confirmed_mats += 1
                if t in ("FERT", "HALB"):
                    made_n += 1
                else:
                    bought_n += 1
            rows.append({"mat": m, "type": t or "?", "objects": detail})
            done += 1
            if done % 10 == 0 or done == len(anchor):
                emit(f"[{done}/{len(anchor)}] checked · {len(missing)} missing so far")
    missing.sort()
    unverified.sort()
    rows.sort(key=lambda x: int(x["mat"]) if str(x["mat"]).isdigit() else 0)
    passed = not missing

    def _cell(d):                                        # one object -> 'id' | '—MISSING' | '?unread'
        if not d:
            return ""
        if d["status"] == "ok":
            return str(d.get("id") or "✓")
        return "—MISSING" if d["status"] == "missing" else "?unread"

    lines = [f"GENESIS VERIFICATION (deterministic, ~0 tokens) — {len(anchor)} materials "
             f"({made_n} made, {bought_n} bought)",
             f"materials confirmed : {confirmed_mats}/{len(anchor)}",
             "",
             f"{'material':>8}  {'type':<5} {'plant':<9} {'BOM/PIR':<12} {'routing/cost':<13} {'prod.ver':<9}"]
    for r in rows:                                       # DETAIL: name every object id per material
        o = r["objects"]
        cp = _cell(o.get("plant view"))
        if r["type"] in ("FERT", "HALB"):
            c1, c2, c3 = _cell(o.get("BOM")), _cell(o.get("routing")), _cell(o.get("production version"))
        else:
            c1, c2, c3 = _cell(o.get("PIR")), _cell(o.get("cost condition")), ""
        lines.append(f"{r['mat']:>8}  {r['type']:<5} {cp:<9} {c1:<12} {c2:<13} {c3:<9}")
    if unverified:
        lines.append("")
        lines.append(f"UNVERIFIED ({len(unverified)}) — read failed after retries, NOT a gap: "
                     + ", ".join(unverified[:12]) + (" …" if len(unverified) > 12 else ""))
    if missing:
        lines.append("")
        lines.append(f"MISSING ({len(missing)}):")
        for g in missing:
            lines.append(f"  MISSING {g}")            # 'MISSING <mat> <object>' -> heal loop's _gap_summary
    lines.append("")
    lines.append("VERDICT: " + ("ALL OBJECTS VERIFIED ✓" if passed else f"{len(missing)} MISSING"))
    data = {"kind": "genesis_verification", "plant": plant, "total": len(anchor),
            "confirmed": confirmed_mats, "made": made_n, "bought": bought_n,
            "passed": passed, "missing": len(missing), "unverified": len(unverified),
            "missing_list": missing, "unverified_list": unverified, "rows": rows}
    return passed, len(missing), len(unverified), "\n".join(lines), data
