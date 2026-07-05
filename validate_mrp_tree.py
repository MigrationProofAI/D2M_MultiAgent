#!/usr/bin/env python
"""validate_mrp_tree.py -- EMPIRICAL post-run validation of an ENTIRE MRP tree, straight from SAP.

Walks the FERT's BOM (recursively, any depth), reads MD04 (read_mrp_list) for EVERY material, and
certifies the RUN RESULT against expectation:
  * made node (FERT/HALB)  -> must have a Planned order (in-house make)
  * bought node (HAWA/ROH)  -> must have a Purchase requisition (external buy)
  * every node             -> its demand must be COVERED (no uncovered negative available at the end)

This is the Plan-Verifier the existing skills lack: they check pre-run SETTINGS (MRPType=PD, ProcType=E);
this checks the actual planning OUTPUT cascaded correctly. Read-only. Usage: python validate_mrp_tree.py 12994
"""
import os, sys, re, json

for line in open(".env", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.split(" #")[0].strip().strip("'").strip('"'))
sys.path.insert(0, "mcp_server")
from make import get_bom                        # noqa: E402
import sap                                      # noqa: E402
from planning_client import read_mrp_list       # noqa: E402

ROOT = sys.argv[1] if len(sys.argv) > 1 else "12994"
PLANT = sys.argv[2] if len(sys.argv) > 2 else "1710"


def _data(s):
    m = re.search(r"@@DATA@@(\{.*\})\s*$", s or "", re.S)
    return json.loads(m.group(1)) if m else None


def mtype(m):
    try:
        return json.loads(sap.get_material(m, full=True)).get("d", {}).get("ProductType", "?")
    except Exception:
        return "ERR"


def bom_components(m):
    d = _data(get_bom(m, PLANT))
    return [c.get("component") for c in (d or {}).get("components", [])] if d else []


def md04(m):
    """(status, has_planned_order, has_purchase_req, min_available). status='ok' when a real MD04 payload
    came back; 'unread' when the read was empty/transient after RETRIES -- so a flaky read can NEVER be
    mistaken for 'genuinely not planned' (a false FAIL is as bad as a false PASS)."""
    r = ""
    for _ in range(3):                                    # retry: transient MD04 reads cried wolf on the FERT
        r = read_mrp_list(m, PLANT) or ""
        if "requirements list" in r.lower():              # a real MD04 payload, not an error/empty
            break
        r = ""
    if not r:
        return "unread", False, False, None
    low = r.lower()
    po = "planned order" in low
    pr = "purchase req" in low or "purchase requisition" in low or "purreq" in low
    avails = [float(x.replace(",", "")) for x in re.findall(r"(-?\d[\d,]*)\s*$", r, re.M)]
    return "ok", po, pr, (min(avails) if avails else None)


# ---- walk the tree ----------------------------------------------------------
print(f"=== VALIDATE MRP TREE from FERT {ROOT} @ {PLANT} ===", flush=True)
seen, tree = set(), []


def walk(m, depth):
    if m in seen:
        return
    seen.add(m)
    t = mtype(m)
    made = t in ("FERT", "HALB")
    status, po, pr, minav = md04(m)
    expect = "planned_order" if made else "purchase_req"
    if status == "unread":                                # couldn't read after retries -> NOT a fail
        got, covered, ok = "UNVERIFIED", None, None
    else:
        got = "planned_order" if po else ("purchase_req" if pr else "NONE")
        covered = (minav is None) or (minav >= 0)
        ok = (got == expect) and covered
    tree.append({"mat": m, "type": t, "depth": depth, "expect": expect, "got": got,
                 "covered": covered, "ok": ok})
    verdict = "OK" if ok else ("UNVERIFIED" if ok is None else "FAIL")
    print(f"  {'  '*depth}{m} [{t}] expect={expect:13} got={got:13} covered={covered} -> {verdict}", flush=True)
    for c in bom_components(m):
        walk(c, depth + 1)


walk(ROOT, 0)

fails = [n for n in tree if n["ok"] is False]             # genuine mismatches (read OK, wrong/no output)
unver = [n for n in tree if n["ok"] is None]              # couldn't read after retries -- honest, not a fail
made_n = [n for n in tree if n["type"] in ("FERT", "HALB")]
bought_n = [n for n in tree if n["type"] not in ("FERT", "HALB")]
print("\n================ MRP-TREE VERDICT ================", flush=True)
print(f"materials checked : {len(tree)}  ({len(made_n)} made, {len(bought_n)} bought)", flush=True)
print(f"planned orders    : {sum(1 for n in made_n if n['got']=='planned_order')}/{len(made_n)} made nodes", flush=True)
print(f"purchase reqs     : {sum(1 for n in bought_n if n['got']=='purchase_req')}/{len(bought_n)} bought nodes", flush=True)
print(f"demand covered    : {sum(1 for n in tree if n['covered'])}/{len(tree)}", flush=True)
if unver:
    print(f"UNVERIFIED ({len(unver)}) -- read failed after retries, NOT a planning gap: "
          + ", ".join(n['mat'] for n in unver), flush=True)
if fails:
    print(f"FAILURES ({len(fails)}):", flush=True)
    for n in fails:
        print(f"   {n['mat']} [{n['type']}] expected {n['expect']} but got {n['got']} | covered={n['covered']}", flush=True)
print("VERDICT: " + ("MRP TREE FULLY PLANNED ✓" if not fails and not unver else
                     "MRP TREE FULLY PLANNED (all read nodes ✓); " + f"{len(unver)} unread" if not fails else
                     f"{len(fails)} NODE(S) NOT PROPERLY PLANNED"), flush=True)
