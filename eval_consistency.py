"""Phase 3 -- Genesis consistency / convergence eval.  READ-ONLY, does NOT touch the running app.

Runs the genesis DECOMPOSITION (vision -> spec) N times on ONE fixed input at PREVIEW level (confirm is
FORCED false -> zero SAP writes), captures each run's OBJECT FOOTPRINT per logical part (type, own BOM,
routing work-centers, PIR/vendor, cost, production version), aligns like-for-like parts across runs, and
emits a per-part per-object-type CONSISTENCY SIGNATURE -- designed to REVEAL divergence, not just confirm
it. Persists every run + the signature to S3 d2m/evals/{batch}/.

    python eval_consistency.py [N] [image_path]        # default N=5, a drone asset

The question it answers: run the same input N times -- are the like-for-like objects (materials, BOMs,
routings, PIRs, costs, PVs) created ALIKE, or do they diverge (a part flips HALB<->HAWA, loses its
routing, changes work-center/vendor)?
"""
import os
import sys
import json
import glob
import tempfile
import datetime
import collections

# --- isolate + guarantee a cheap, write-free, single-agent decomposition path ---
os.environ["RIG_SESSIONS_DIR"] = tempfile.mkdtemp(prefix="evalsess_")   # don't pollute real sessions/
os.environ.setdefault("RIG_ORCHESTRATE", "off")                        # decomposition only -- no heal/board
os.environ.setdefault("GENESIS_DEDUP", "off")                          # fresh classification each run

from dotenv import load_dotenv
load_dotenv()

from memory import TieredMemory
from session import Session
from agent import run_turn
from genesis_mode import GENESIS_PERSONA
from model_client import GENESIS_MODEL, MODEL_PROVIDER
import tools as _tools

# --- SAFETY: force EVERY run_genesis call to PREVIEW (confirm=False) at DISPATCH (what run_turn calls),
#     so the eval can NEVER write to SAP -- regardless of what confirm the model passes. ---
import agent as _agentmod
_real_dispatch = _agentmod.dispatch
def _safe_dispatch(name, args):
    if name == "run_genesis":
        args = dict(args or {}); args["confirm"] = False
    return _real_dispatch(name, args)
_agentmod.dispatch = _safe_dispatch

# treat every part as NEW so the preview needs NO SAP reads -> the eval touches only the model (AI Core).
import mcp_server.genesis as _genesis
_genesis._exists = lambda m: False

EVAL_PROMPT = ("This is a product assembly. Build the full Design2Make genesis for it: perceive every "
               "part, classify made (HALB) vs bought (HAWA), decompose each made sub-assembly into its "
               "raws, and call run_genesis to PREVIEW the plan (confirm=false). Do not ask me anything.")


def _norm(s):
    return " ".join((s or "").lower().split())


def _wcs(routing):
    return [o.get("work_center") for o in (routing or []) if o.get("work_center")]


def _footprint(spec):
    """Flatten a genesis spec tree -> {part_key: {name, type, role, has_bom, routing_wcs, has_pir,
    vendor, has_cost, has_pv}} -- the object footprint each logical part is planned to receive."""
    parts = {}
    parent = spec.get("parent") or {}
    if parent.get("description"):
        parts[_norm(parent.get("description"))] = {
            "name": parent.get("description"), "type": parent.get("type", "FERT"), "role": "made",
            "has_bom": bool(spec.get("components")), "routing_wcs": _wcs(spec.get("routing")),
            "has_pir": False, "vendor": None, "has_cost": False, "has_pv": True}

    def _walk(comps):
        for c in comps:
            kids = c.get("components") or []
            made = (c.get("role") == "made") or (c.get("type") in ("HALB", "FERT"))
            bought = c.get("role") == "bought"
            parts[_norm(c.get("description") or c.get("name"))] = {
                "name": c.get("name") or c.get("description"), "type": c.get("type"),
                "role": c.get("role"), "has_bom": bool(kids), "routing_wcs": _wcs(c.get("routing")),
                "has_pir": bool(c.get("vendor")) and bought, "vendor": c.get("vendor") if bought else None,
                "has_cost": (c.get("price") not in (None, "")) and bought, "has_pv": made}
            if kids:
                _walk(kids)
    _walk(spec.get("components") or [])
    return parts


def _counts(fp):
    """Aggregate object counts for one run's footprint (robust to naming -- no alignment needed)."""
    by_type = collections.Counter(p["type"] for p in fp.values())
    return {"materials": len(fp), "by_type": dict(by_type),
            "boms": sum(1 for p in fp.values() if p["has_bom"]),
            "routings": sum(1 for p in fp.values() if p["routing_wcs"]),
            "pirs": sum(1 for p in fp.values() if p["has_pir"]),
            "costs": sum(1 for p in fp.values() if p["has_cost"]),
            "pvs": sum(1 for p in fp.values() if p["has_pv"])}


def run_once(i):
    """One headless genesis decomposition. Returns {spec, footprint, counts} or {error}."""
    sess = Session(f"orch-eval-{i}")                 # 'orch-' so it's hidden from the Sessions dropdown
    mem = TieredMemory(sess, system=GENESIS_PERSONA)
    steps = []
    try:
        run_turn(mem, EVAL_PROMPT, image=_IMG_BYTES, mime="image/png", tools=True, max_steps=16,
                 verbose=False, steps=steps, perceive=True, model=GENESIS_MODEL)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:180]}"}
    spec = next((s["args"].get("spec") for s in steps
                 if s.get("kind") == "tool_call" and s.get("tool") == "run_genesis" and s["args"].get("spec")),
                None)
    if not spec:
        return {"error": "model did not call run_genesis (no spec captured)"}
    fp = _footprint(spec)
    return {"spec": spec, "footprint": fp, "counts": _counts(fp)}


def _signature(runs):
    """Per-part per-object-type consistency across the successful runs."""
    ok = [r for r in runs if r.get("footprint")]
    N = len(ok)
    # --- level 1: count stability (naming-robust) ---
    metrics = ["materials", "boms", "routings", "pirs", "costs", "pvs"]
    count_dist = {m: [r["counts"][m] for r in ok] for m in metrics}
    type_dist = collections.Counter()
    for r in ok:
        for t, c in r["counts"]["by_type"].items():
            type_dist[t] += 0                      # ensure key exists
    per_run_types = [r["counts"]["by_type"] for r in ok]
    # --- level 2: align like-for-like parts by normalized name ---
    keys = collections.Counter()
    for r in ok:
        keys.update(r["footprint"].keys())
    parts = []
    for k, seen in keys.most_common():
        fps = [r["footprint"].get(k) for r in ok]
        present = [f for f in fps if f]
        types = [f["type"] for f in present]
        wcs = [tuple(f["routing_wcs"]) for f in present]
        vendors = [f["vendor"] for f in present if f["role"] == "bought"]
        parts.append({
            "part": present[0]["name"], "seen_in": seen, "of": N,
            "type": collections.Counter(types).most_common(),
            "type_stable": len(set(types)) == 1,
            "has_bom": [f["has_bom"] for f in present],
            "routing_wcs": collections.Counter(wcs).most_common(),
            "has_pir": [f["has_pir"] for f in present],
            "vendor_stable": len(set(vendors)) <= 1,
            "has_pv": [f["has_pv"] for f in present],
            "diverges": (seen < N) or (len(set(types)) > 1) or (len(set(wcs)) > 1)})
    return {"runs_ok": N, "count_dist": count_dist, "per_run_by_type": per_run_types, "parts": parts}


def _report(sig, meta):
    L = []
    L.append(f"═══ GENESIS CONSISTENCY SIGNATURE ═══  ({meta['runs_ok']}/{meta['N']} runs ok · "
             f"model={meta['provider']} · thinking={meta['thinking']})")
    if sig["runs_ok"] == 0:
        L.append("\n  ✗ 0 runs succeeded — nothing to compare. See the per-run errors above.")
        return "\n".join(L)
    L.append("\n— OBJECT COUNTS PER RUN (are the totals stable?) —")
    for m, vals in sig["count_dist"].items():
        uniq = set(vals)
        flag = "" if len(uniq) == 1 else "  ⚠ VARIES"
        L.append(f"  {m:10} {vals}   mode={collections.Counter(vals).most_common(1)[0][0]}{flag}")
    L.append(f"  by_type per run: {sig['per_run_by_type']}")
    L.append("\n— PER-PART OBJECT FOOTPRINT (like-for-like across runs) —")
    L.append(f"  {'part':30} {'seen':6} {'type':22} {'routing WCs':22} {'PV/BOM/PIR'}")
    for p in sorted(sig["parts"], key=lambda x: (not x["diverges"], -x["seen_in"])):
        mark = "⚠ " if p["diverges"] else "  "
        typ = ",".join(f"{t}×{n}" for t, n in p["type"])
        wc = ",".join(f"{'/'.join(w) or '-'}×{n}" for w, n in p["routing_wcs"])[:20]
        pv = f"pv{sum(p['has_pv'])}/{len(p['has_pv'])} bom{sum(p['has_bom'])} pir{sum(p['has_pir'])}"
        L.append(f"{mark}{p['part'][:30]:30} {p['seen_in']}/{p['of']:<4} {typ[:22]:22} {wc:22} {pv}")
    div = [p for p in sig["parts"] if p["diverges"]]
    L.append(f"\n— DIVERGENCES: {len(div)} part(s) not created alike across all runs —")
    for p in div:
        why = []
        if p["seen_in"] < p["of"]:
            why.append(f"absent in {p['of']-p['seen_in']} run(s)")
        if not p["type_stable"]:
            why.append("TYPE FLIPS " + "/".join(f"{t}×{n}" for t, n in p["type"]))
        if len(p["routing_wcs"]) > 1:
            why.append("WC drift")
        L.append(f"  ⚠ {p['part'][:34]}: {'; '.join(why)}")
    if not div:
        L.append("  ✅ none — every part got an identical object footprint in all runs.")
    return "\n".join(L)


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    img = sys.argv[2] if len(sys.argv) > 2 else None
    if not img:
        cands = glob.glob("sessions/*/assets/*.png")
        if not cands:
            print("No image found. Pass one: python eval_consistency.py 5 <image.png>"); return
        img = max(cands, key=os.path.getsize)        # biggest png ~ the assembly photo
    global _IMG_BYTES
    _IMG_BYTES = open(img, "rb").read()
    meta = {"N": N, "provider": MODEL_PROVIDER, "thinking": os.getenv("RIG_THINKING", "off"),
            "model": GENESIS_MODEL, "image": img, "prompt": EVAL_PROMPT}
    print(f"▶ consistency eval: N={N} · image={img} ({len(_IMG_BYTES)//1024}KB) · "
          f"provider={meta['provider']} · thinking={meta['thinking']}  (PREVIEW ONLY -- no SAP writes)\n")
    runs = []
    for i in range(N):
        print(f"  run {i+1}/{N} …", flush=True)
        r = run_once(i)
        if r.get("error"):
            print(f"    ! {r['error']}")
        else:
            print(f"    ok: {r['counts']}")
        runs.append(r)
    sig = _signature(runs)
    meta["runs_ok"] = sig["runs_ok"]
    report = _report(sig, meta)
    print("\n" + report)
    _persist(meta, runs, sig, report)


def _persist(meta, runs, sig, report):
    """Persist the batch to S3 d2m/evals/{batch}/ (run records + signature + readable report)."""
    if not (os.getenv("S3_BUCKET")):
        print("\n(S3_BUCKET not set -- skipped S3 persist)"); return
    try:
        import boto3
        c = boto3.client("s3", region_name=os.getenv("S3_REGION", "us-west-1"))
        bk = os.getenv("S3_BUCKET"); px = os.getenv("S3_PREFIX", "d2m")
        batch = "batch-" + datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
        base = f"{px}/evals/{batch}"
        c.put_object(Bucket=bk, Key=f"{base}/meta.json", Body=json.dumps(meta, indent=2).encode())
        c.put_object(Bucket=bk, Key=f"{base}/signature.json", Body=json.dumps(sig, indent=2, default=str).encode())
        c.put_object(Bucket=bk, Key=f"{base}/report.txt", Body=report.encode("utf-8"))
        for i, r in enumerate(runs):
            c.put_object(Bucket=bk, Key=f"{base}/run_{i}.json", Body=json.dumps(r, indent=2, default=str).encode())
        print(f"\n✅ persisted to s3://{bk}/{base}/  ({len(runs)} runs + signature + report)")
    except Exception as e:
        print(f"\n(S3 persist failed: {e})")


if __name__ == "__main__":
    main()
