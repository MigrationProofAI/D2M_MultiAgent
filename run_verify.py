"""VERIFY-LOOP proof — the fix for session 903d6806's "claimed done, but wasn't".

Three parts, each an assertion (exits non-zero on failure):

  A. AUTHORITY (deny-test, OFFLINE/deterministic) — a read-only agent that TRIES to write is DENIED
     at dispatch; a read it IS allowed goes through. No model, no SAP — monkeypatched. This proves the
     one new mechanism (least-privilege tool binding) actually has teeth.

  B. LOOP CONTROL (OFFLINE/deterministic) — run_doer_critic loops while the critic says FAIL and stops
     on PASS, capped. Monkeypatched subagents — proves the control flow, no model/SAP.

  C. LIVE VERIFIER (hits SAP read-back) — the genesis-verifier agent, given the EXACT false claim from
     903d6806, re-reads SAP and returns VERDICT: FAIL (it catches the missing/unverifiable objects the
     doer reported as "all green"). Run from conda base with MODEL_PROVIDER=anthropic.

    $env:MODEL_PROVIDER = "anthropic"
    python run_verify.py
"""
import sys
import re
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


def _last_verdict(text):
    """Read the FINAL 'VERDICT: PASS|FAIL' line (the agent's binding judgement)."""
    hits = re.findall(r"VERDICT:\s*(PASS|FAIL)", text or "", re.IGNORECASE)
    return hits[-1].upper() if hits else None


def verify_passes(text):
    return _last_verdict(text) == "PASS"


# ---------------------------------------------------------------------------
# A. AUTHORITY deny-test (offline) — monkeypatch the model to ATTEMPT a write; assert it's denied.
# ---------------------------------------------------------------------------
def test_authority():
    import agent
    from model_client import _Msg, _TC
    from orchestrate import READ_ONLY_TOOLS
    from memory import TieredMemory
    from session import Session

    calls = {"dispatched": []}
    real_dispatch = agent.dispatch
    agent.dispatch = lambda name, args: (calls["dispatched"].append(name) or "OK (stubbed)")

    def scripted_model(forced_tool, forced_args):
        seq = iter([
            _Msg("", [_TC("c1", forced_tool, forced_args)]),   # step 1: try the tool
            _Msg("done", None),                                  # step 2: finish
        ])
        return lambda messages, tools=None, model=None, temperature=0.2: next(seq)

    def run_once(forced_tool, forced_args):
        calls["dispatched"].clear()
        agent.model_complete = scripted_model(forced_tool, forced_args)
        sess = Session("verify-denytest")
        mem = TieredMemory(sess, system="test")
        steps = []
        agent.run_turn(mem, "do it", tools=True, allowed_tools=READ_ONLY_TOOLS,
                       max_steps=4, verbose=False, steps=steps)
        denied = any(s.get("kind") == "tool_result" and "DENIED" in str(s.get("result", "")) for s in steps)
        return denied, list(calls["dispatched"])

    try:
        # 1) a WRITE the read-only agent is not allowed -> DENIED, never dispatched
        denied_w, dispatched_w = run_once("create_material", '{"fields":{},"confirm":true}')
        assert denied_w, "write was NOT denied — authority has no teeth"
        assert "create_material" not in dispatched_w, "DENIED write still reached dispatch!"
        # 2) a READ the agent IS allowed -> goes through, no denial
        denied_r, dispatched_r = run_once("get_material", '{"material_id":"11728"}')
        assert not denied_r, "an allowed read was wrongly denied"
        assert "get_material" in dispatched_r, "allowed read never dispatched"
    finally:
        agent.dispatch = real_dispatch
        import model_client
        agent.model_complete = model_client.model_complete
        import shutil
        shutil.rmtree(Path("sessions/verify-denytest"), ignore_errors=True)

    print("A. AUTHORITY  ✅  write DENIED (not dispatched), allowed read went through")


# ---------------------------------------------------------------------------
# B. LOOP control-flow (offline) — monkeypatch subagent to a scripted doer/critic.
# ---------------------------------------------------------------------------
def test_loop_control():
    import orchestrate
    real_sub = orchestrate.subagent
    # critic says FAIL, FAIL, then PASS -> loop should run 3 iters and end ok
    verdicts = iter(["...\nVERDICT: FAIL\nmissing X", "...\nVERDICT: FAIL\nstill missing X",
                     "...\nVERDICT: PASS\nall confirmed"])

    def fake_sub(role_system, task, **kw):
        label = kw.get("label", "")
        if label.startswith("critic"):
            return next(verdicts)
        return f"doer acted (saw: {'gap' if 'NOT COMPLETE' in task else 'fresh task'})"

    orchestrate.subagent = fake_sub
    try:
        res = orchestrate.run_doer_critic("doer", "critic", "make 3 things", verify_passes, max_iters=5)
        assert res["ok"] is True, "loop did not converge on PASS"
        assert res["iters"] == 3, f"expected 3 iters, got {res['iters']}"
        # and a loop that never passes must stop at the cap, ok=False
        always_fail = iter(["VERDICT: FAIL"] * 10)
        orchestrate.subagent = lambda rs, t, **kw: (next(always_fail) if kw.get("label", "").startswith("critic")
                                                    else "doer acted")
        res2 = orchestrate.run_doer_critic("doer", "critic", "task", verify_passes, max_iters=2)
        assert res2["ok"] is False and res2["iters"] == 2, "cap not enforced on perpetual FAIL"
    finally:
        orchestrate.subagent = real_sub
    print("B. LOOP       ✅  re-loops on FAIL, stops on PASS, caps on perpetual FAIL")


# ---------------------------------------------------------------------------
# C. PARSE (offline) — the structured verdict tail drives the heal loop. Counts must parse.
# ---------------------------------------------------------------------------
def test_parse():
    from orchestrate import parse_verdict
    p, m, u, _ = parse_verdict("...table...\nVERDICT: FAIL\nGAPS: missing=4, unverified=8")
    assert (p, m, u) == (False, 4, 8), (p, m, u)
    p, m, u, _ = parse_verdict("all good\nVERDICT: PASS\nGAPS: missing=0, unverified=0")
    assert (p, m, u) == (True, 0, 0), (p, m, u)
    p, m, u, _ = parse_verdict("VERDICT: FAIL")          # FAIL w/o counts -> assume a fixable gap
    assert (p, m, u) == (False, 1, 0), (p, m, u)
    print("C. PARSE      ✅  VERDICT + missing/unverified counts parse (drives the heal loop)")


# ---------------------------------------------------------------------------
# D. LIVE spec-driven verifier — does it catch the HALB-BOM gap from 67664336?
# ---------------------------------------------------------------------------
# The doer's turn-9 "COMPLETE" claim from 67664336: FERT BOM only; the 4 HALB BOMs were never built.
FALSE_CLAIM_67664336 = """## 🚲 Bicycle BOM Genesis — COMPLETE ✅ @ plant 1710
Materials: FERT 11747 Bicycle; HALB 11748 Wheel, 11749 Frame, 11750 Handlebar, 11751 Seat.
BOM 00000505 (11747 -> the 4 HALBs) — 4 components confirmed.
Routing 50000320 + Production Version 0001 created."""


def test_live_spec_verifier():
    from orchestrate import verify_claim
    print("\n--- D: spec-driven verifier on 67664336 (expect FAIL, HALB BOMs MISSING) ---")
    passed, missing, unverified, verdict = verify_claim(FALSE_CLAIM_67664336, label="verifier", max_steps=16)
    print(verdict)
    print(f"\n>>> parsed: passed={passed} missing={missing} unverified={unverified}")
    assert passed is False, "verifier wrongly PASSED a half-finished genesis"
    assert missing >= 1, f"verifier did not flag any MISSING HALB BOM (missing={missing})"
    halb_hits = sum(h in (verdict or "") for h in ("11748", "11749", "11750", "11751"))
    assert halb_hits >= 3, f"verifier did not independently check the HALB sub-assemblies (hits={halb_hits})"
    print("D. LIVE       ✅  spec-driven verifier proactively caught the missing HALB BOMs")


if __name__ == "__main__":
    print("=" * 78)
    print("VERIFY + AUTO-HEAL PROOF  —  doer/critic gate (fix for 903d6806 / 67664336)")
    print("=" * 78)
    test_authority()            # offline
    test_loop_control()         # offline
    test_parse()                # offline
    test_live_spec_verifier()   # live SAP read-back, spec-driven
    print("\n" + "=" * 78)
    print("ALL PASSED — authority has teeth, the loop caps, counts parse, the verifier catches the HALB gap.")
    print("=" * 78)
