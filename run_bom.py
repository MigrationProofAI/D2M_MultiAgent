#!/usr/bin/env python
"""run_bom.py -- drive genesis from a tabbed-Excel BOM, DETERMINISTICALLY (no vision model). Scale-test
genesis at 50/100/150/200 materials.

  python run_bom.py bom_50.xlsx              # PREVIEW (no SAP writes) + planned counts
  python run_bom.py bom_50.xlsx --runs 5     # parse 5x; counts must be identical (deterministic)
  python run_bom.py bom_50.xlsx --commit     # COMMIT to SAP (needs .env creds; GENESIS_DEDUP=off)

Run from the repo root in the conda base env (openpyxl + SAP creds in .env). The counts mirror
eval_consistency._footprint/_counts (materials/BOMs/routings/PIRs/costs/PVs straight off the spec)."""
import os
import sys
import time
import json
import argparse
import collections

os.environ.setdefault("GENESIS_DEDUP", "off")          # fresh creates; read at genesis import time
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # preview uses box-drawing chars
except Exception:
    pass
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "mcp_server"))
sys.path.insert(0, _HERE)

from excel_bom import genesis_from_excel                # noqa: E402


def _norm(s):
    return " ".join((s or "").lower().split())


def _wcs(routing):
    return [o.get("work_center") for o in (routing or []) if o.get("work_center")]


def _footprint(spec):
    """Object footprint per logical part (mirrors eval_consistency._footprint)."""
    parts = {}
    parent = spec.get("parent") or {}
    if parent.get("description"):
        parts[_norm(parent["description"])] = {
            "type": parent.get("type", "FERT"), "has_bom": bool(spec.get("components")),
            "wcs": _wcs(spec.get("routing")), "has_pir": False, "has_cost": False, "has_pv": True}

    def walk(comps):
        for c in comps:
            kids = c.get("components") or []
            made = c.get("role") == "made" or c.get("type") in ("HALB", "FERT")
            bought = c.get("role") == "bought"
            parts[_norm(c.get("description") or c.get("name"))] = {
                "type": c.get("type"), "has_bom": bool(kids), "wcs": _wcs(c.get("routing")),
                "has_pir": bool(c.get("vendor")) and bought,
                "has_cost": (c.get("price") not in (None, "")) and bought, "has_pv": made}
            if kids:
                walk(kids)
    walk(spec.get("components") or [])
    return parts


def _counts(fp):
    by_type = collections.Counter(p["type"] for p in fp.values())
    return {"materials": len(fp), "by_type": dict(by_type),
            "boms": sum(1 for p in fp.values() if p["has_bom"]),
            "routings": sum(1 for p in fp.values() if p["wcs"]),
            "pirs": sum(1 for p in fp.values() if p["has_pir"]),
            "costs": sum(1 for p in fp.values() if p["has_cost"]),
            "pvs": sum(1 for p in fp.values() if p["has_pv"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--commit", action="store_true", help="write to SAP (default: preview only)")
    ap.add_argument("--runs", type=int, default=1, help="parse N times and assert identical counts")
    args = ap.parse_args()

    t0 = time.time()
    spec, warnings = genesis_from_excel(args.file)
    print(f"parsed {args.file} in {time.time() - t0:.2f}s")
    for w in warnings:
        print(f"  WARN: {w}")
    counts = _counts(_footprint(spec))
    print("planned counts:", json.dumps(counts))

    if args.runs > 1:
        base = json.dumps(counts, sort_keys=True)
        allok = True
        for i in range(args.runs):
            c = json.dumps(_counts(_footprint(genesis_from_excel(args.file)[0])), sort_keys=True)
            ok = (c == base)
            allok = allok and ok
            print(f"  run {i + 1}: {'IDENTICAL' if ok else 'DIFFERS -> BUG'}")
        print("determinism:", "PASS" if allok else "FAIL")
        return

    from genesis import run_genesis                     # heavy import; after parse so a bad file fails fast
    print(f"\n=== run_genesis(confirm={args.commit}) ===")
    t1 = time.time()
    out = run_genesis(spec, confirm=args.commit)
    print(str(out)[:3000])
    print(f"\n{'COMMITTED' if args.commit else 'PREVIEW'} in {time.time() - t1:.1f}s")


if __name__ == "__main__":
    main()
