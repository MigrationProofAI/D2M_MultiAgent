#!/usr/bin/env python
"""verify_ebike.py -- EMPIRICAL verification of a committed genesis tree, straight from SAP.
Walks the FERT's BOM (and each HALB's BOM), then checks every object actually exists:
materials by type, a BOM+routing on each made node, and PIR+cost on every bought leaf.
Prints real gaps (not model narration). Usage: python verify_ebike.py 12778"""
import os, sys, json, re

for line in open(".env", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.split(" #")[0].strip().strip("'").strip('"'))
sys.path.insert(0, "mcp_server")
from make import get_bom, read_pir, read_cost_condition          # noqa: E402
from genesis import read_routing                                 # noqa: E402
import sap                                                       # noqa: E402

ROOT = sys.argv[1] if len(sys.argv) > 1 else "12778"


def _data(s):
    m = re.search(r"@@DATA@@(\{.*\})\s*$", s or "", re.S)
    return json.loads(m.group(1)) if m else None


def mtype(m):
    try:
        return json.loads(sap.get_material(m, full=True)).get("d", {}).get("ProductType", "?")
    except Exception:
        return "ERR"


def bom_components(m):
    d = _data(get_bom(m))
    return [c.get("component") for c in (d or {}).get("components", [])] if d else []


def has_pir(m):
    r = read_pir(m) or ""
    return ("info record" in r.lower() and "17300001" in r), r.splitlines()[0][:80]


def has_cost(m):
    r = read_cost_condition(m) or ""
    ok = bool(re.search(r"\d+\.\d+", r)) and "no " not in r.lower()[:20]
    return ok, r.splitlines()[0][:80]


def has_routing(m):
    r = read_routing(m) or ""
    return ("group" in r.lower() or "operation" in r.lower()) and "no " not in r.lower()[:15], r.splitlines()[0][:80]


print(f"=== VERIFY genesis tree from FERT {ROOT} ===", flush=True)
root_type = mtype(ROOT)
direct = bom_components(ROOT)
print(f"FERT {ROOT} [{root_type}] -> BOM with {len(direct)} direct components", flush=True)

made = [(ROOT, root_type)]        # (matnr, type) needing BOM+routing
bought = []                        # matnr needing PIR+cost
halb_boms = {ROOT: len(direct)}

for c in direct:
    t = mtype(c)
    if t in ("HALB", "FERT"):
        kids = bom_components(c)
        halb_boms[c] = len(kids)
        made.append((c, t))
        for k in kids:
            bought.append(k)      # HALB raws are bought leaves
    else:
        bought.append(c)          # top-level bought

# de-dup (a shared part would show twice -- worth knowing)
bought_unique = sorted(set(bought))
print(f"\nSTRUCTURE: {len(made)} made node(s) (1 FERT + {len(made)-1} HALB), "
      f"{len(bought)} bought slot(s) ({len(bought_unique)} unique materials)", flush=True)
total_mats = len(made) + len(bought_unique)
print(f"TOTAL distinct materials in tree: {total_mats}", flush=True)

print("\n--- BOM per made node (item counts) ---", flush=True)
missing_bom = [m for m, _ in made if halb_boms.get(m, 0) == 0]
for m, t in made:
    print(f"  {m} [{t}]: BOM {halb_boms.get(m,0)} item(s)" + ("  <<< NO BOM" if halb_boms.get(m,0)==0 else ""), flush=True)

print("\n--- routing per made node ---", flush=True)
no_routing = []
for m, t in made:
    ok, line = has_routing(m)
    if not ok: no_routing.append(m)
    print(f"  {m}: {'OK' if ok else 'MISSING'}  {line}", flush=True)

print(f"\n--- PIR + cost on {len(bought_unique)} bought materials ---", flush=True)
no_pir, no_cost = [], []
for i, m in enumerate(bought_unique):
    pok, pl = has_pir(m)
    cok, cl = has_cost(m)
    if not pok: no_pir.append(m)
    if not cok: no_cost.append(m)
    flag = "" if (pok and cok) else "   <<< " + ("noPIR " if not pok else "") + ("noCOST" if not cok else "")
    print(f"  [{i+1:3}/{len(bought_unique)}] {m}: PIR {'ok' if pok else 'NO'} | cost {'ok' if cok else 'NO'}{flag}", flush=True)

print("\n================ SUMMARY ================", flush=True)
print(f"materials      : {total_mats}", flush=True)
print(f"made nodes     : {len(made)}  (BOM missing: {missing_bom or 'none'})", flush=True)
print(f"routings       : {len(made)-len(no_routing)}/{len(made)} ok  (missing: {no_routing or 'none'})", flush=True)
print(f"PIRs           : {len(bought_unique)-len(no_pir)}/{len(bought_unique)} ok  (missing: {no_pir or 'none'})", flush=True)
print(f"costs          : {len(bought_unique)-len(no_cost)}/{len(bought_unique)} ok  (missing: {no_cost or 'none'})", flush=True)
print("VERDICT: " + ("ALL OBJECTS PRESENT ✓" if not (missing_bom or no_routing or no_pir or no_cost)
                     else "GAPS FOUND (see above)"), flush=True)
