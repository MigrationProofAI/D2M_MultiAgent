"""GATE -- VERIFIED COMPLETION (Problem B1 + B2). Three teeth, all offline/deterministic:

  B1  the maker reconciles its OWN create-loop: a run that creates fewer materials than the spec it
      received ends "GENESIS INCOMPLETE" with a typed IncompleteCreation{planned, created, missing} --
      NEVER "GENESIS COMPLETE" (the 15-of-28 silent success).
  B2a completion/verification questions are CLASSIFIED at dispatch (is_completion_question) so they
      route to the Verifier's reconciliation -- never the Guide's narration, never a doer's optimism --
      while build commands ("go ahead, create them all") stay untouched.
  B2b manifest reconciliation emits the typed ReconciliationReport{planned, created, missing, extra,
      verdict}: a planned-but-never-created node is MISSING (the gap a created-anchored verify can
      structurally not see); a genuinely complete run reconciles to zero-missing.

    uv run python gate_reconciliation.py
"""
import sys, json, copy
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "mcp_server")

import genesis, discipline

# --- stub every writer/read so the gate is offline + deterministic --------------------------------
discipline.Spine._persist_ledger = lambda self: None            # no repo-root sidecar writes from a gate
discipline.Spine._persist_kg = lambda self: None
genesis._DEDUP_DEFAULT = False                                  # fresh build, no vector engine
genesis._exists = lambda m: False
genesis._readback = lambda m: {"Product": m}
genesis._vec_add = lambda *a, **k: None
genesis.create_info_record = lambda *a, **k: "Created info record 5300000001"
genesis.create_cost_condition = lambda *a, **k: "Created cost condition 0000000001"
genesis.create_bom = lambda *a, **k: "BOM created ok"
genesis.create_routing = lambda *a, **k: "routing created ok"
genesis._create_production_version = lambda m, p, d: (True, "ok")

_next = {"n": 12000}
FAIL = set()


def _fake_create(spec, plant):
    name = spec.get("name") or spec.get("description")
    if name in FAIL:
        return None, "SAP request failed 400: gate-forced create failure"
    _next["n"] += 1
    return str(_next["n"]), f'Created "Product":"{_next["n"]}"'


genesis._create_material = _fake_create

SPEC = {"parent": {"description": "Gate Laptop", "type": "FERT"},
        "components": [
            {"name": "CPU", "description": "CPU", "type": "HAWA", "role": "bought",
             "vendor": "17300001", "price": 100, "quantity": 1},
            {"name": "RAM", "description": "RAM", "type": "HAWA", "role": "bought",
             "vendor": "17300001", "price": 50, "quantity": 2},
            {"name": "SSD", "description": "SSD", "type": "HAWA", "role": "bought",
             "vendor": "17300001", "price": 80, "quantity": 1},
            {"name": "CHASSIS", "description": "Chassis Assembly", "type": "HALB", "role": "made",
             "quantity": 1,
             "components": [{"name": "FRAME", "description": "Frame", "type": "ROH", "role": "bought", "quantity": 1},
                            {"name": "SCREWS", "description": "Screws", "type": "ROH", "role": "bought", "quantity": 8}],
             "routing": [{"operation": "10", "text": "Assemble", "work_center": "ASSEMBLY"}]}]}
# planned nodes = parent + CPU + RAM + SSD + CHASSIS + FRAME + SCREWS = 7


def _data(out):
    return json.loads(out.split("@@DATA@@", 1)[1]) if "@@DATA@@" in out else {}


# --- B1: forced under-delivery -> typed IncompleteCreation, NOT success ---------------------------
FAIL = {"CPU", "RAM"}
out = genesis.run_genesis(copy.deepcopy(SPEC), confirm=True)
d = _data(out)
inc = d.get("incomplete") or {}
b1a = "GENESIS INCOMPLETE" in out and "GENESIS COMPLETE" not in out
b1b = inc.get("kind") == "IncompleteCreation" and inc.get("planned") == 7 and inc.get("created") == 5
b1c = set(inc.get("missing") or []) == {"CPU", "RAM"}
b1d = "MISSING CPU" in out and "MISSING RAM" in out            # the report NAMES the gap

# --- B1: a genuinely complete run reconciles to zero-missing BEFORE saying complete ---------------
FAIL = set()
out2 = genesis.run_genesis(copy.deepcopy(SPEC), confirm=True)
d2 = _data(out2)
rec2 = d2.get("reconciliation") or {}
b1e = "GENESIS COMPLETE" in out2 and "reconciled 7/7" in out2
b1f = rec2.get("complete") is True and rec2.get("planned") == 7 and not d2.get("incomplete")

# --- B2a: the completion-question classifier at dispatch ------------------------------------------
from guide import is_completion_question, is_platform_question

POS = ["is everything created?", "did everything get created", "Is it all there?",
       "ensure all objects were created", "check that all 28 parts are in SAP",
       "verify everything was created correctly", "was everything built?",
       "anything missing?", "reconcile against the manifest", "make sure all the materials exist",
       "confirm everything was created"]
NEG = ["go ahead, create them all", "create a material for the wheel", "build this assembly from the image",
       "run mrp for the fg", "create a demand of 100 units every month", "extend the laptop to plant 1010",
       "load bom from bom_50.xlsx", "what is the verifier?", "go ahead"]
pos_hits = [p for p in POS if is_completion_question(p)]
neg_hits = [n for n in NEG if is_completion_question(n)]
b2a = len(pos_hits) == len(POS)
b2b_neg = not neg_hits
b2c = not any(is_platform_question(p) and not is_completion_question(p) for p in POS)

# --- B2b: manifest reconciliation -- typed ReconciliationReport ------------------------------------
import conformance
conformance._expand_tree = lambda a, p: sorted(set(str(x) for x in a))     # no live BOM walk in a gate
conformance._descmap = lambda a: {"gate laptop": "12000", "cpu": "12001", "chassis assembly": "12002",
                                  "frame": "12003", "screws": "12004"}

rep, rec = conformance.reconcile_manifest(copy.deepcopy(SPEC), ["12000", "12001", "12002", "12003", "12004", "12099"], "1710")
b3a = rec["kind"] == "ReconciliationReport" and rec["planned"] == 7 and rec["created"] == 5
b3b = set(rec["missing"]) == {"RAM", "SSD"} and rec["extra"] == ["12099"] and rec["complete"] is False
b3c = "INCOMPLETE" in rec["verdict"] and "MISSING RAM" in rep and "MISSING SSD" in rep

conformance._descmap = lambda a: {"gate laptop": "12000", "cpu": "12001", "ram": "12005", "ssd": "12006",
                                  "chassis assembly": "12002", "frame": "12003", "screws": "12004"}
rep2, rec2b = conformance.reconcile_manifest(copy.deepcopy(SPEC),
                                             ["12000", "12001", "12002", "12003", "12004", "12005", "12006"], "1710")
b3d = rec2b["complete"] is True and "zero missing" in rec2b["verdict"] and not rec2b["extra"]

print("=== GATE (VERIFIED COMPLETION -- B1 maker reconcile + B2 exclusive verdicts) ===")
print(f"  B1 (1) 5-of-7 run says INCOMPLETE, never COMPLETE   : {b1a}")
print(f"  B1 (2) typed IncompleteCreation planned=7 created=5 : {b1b}")
print(f"  B1 (3) missing ids name CPU + RAM                   : {b1c}")
print(f"  B1 (4) report lines name every missing node         : {b1d}")
print(f"  B1 (5) complete run says 'reconciled 7/7'           : {b1e}")
print(f"  B1 (6) zero-missing reconciliation before complete  : {b1f}")
print(f"  B2 (1) completion questions ALL classified          : {b2a}  {('missed: ' + str([p for p in POS if p not in pos_hits])) if not b2a else ''}")
print(f"  B2 (2) build commands NOT hijacked                  : {b2b_neg}  {('hijacked: ' + str(neg_hits)) if neg_hits else ''}")
print(f"  B2 (3) completion beats the Guide's platform regex  : {b2c}")
print(f"  B2 (4) ReconciliationReport planned/created typed   : {b3a}")
print(f"  B2 (5) missing = never-created; extra flagged       : {b3b}")
print(f"  B2 (6) verdict INCOMPLETE + names in the report     : {b3c}")
print(f"  B2 (7) complete run -> zero missing, verdict clean  : {b3d}")
ok = all([b1a, b1b, b1c, b1d, b1e, b1f, b2a, b2b_neg, b2c, b3a, b3b, b3c, b3d])
print(f"\n  ALL PASS: {ok}")
sys.exit(0 if ok else 1)
