"""Generic orchestration patterns we OWN -- not framework objects, just small functions over a
SUBAGENT. These are the agent PATTERNS kept from the ADK shape (sequential / parallel / loop /
hybrid), minus the harness. Compose them for multi-agent flows without importing a framework.

THE KEY IDEA (STARTING_POINT.md): an agent = `run_turn` + an ISOLATED TieredMemory + the subset of
tools its role is allowed to bind. `subagent()` is exactly that -- a fresh Session (its own folder),
a fresh TieredMemory seeded with the role's system prompt, and one `run_turn`. The patterns below are
just orchestrators that call `subagent()` more than once and merge the results. Nothing new under the
hood; the foundation (`run_turn`, `TieredMemory`, `Session`, the model seam) is reused, never rewritten.
"""
import os
import re
import time
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from agent import run_turn
from memory import TieredMemory
from session import Session

_HERE = Path(__file__).resolve().parent

# Master flag. Off by default -> importing this module changes NO existing behaviour; the single-agent
# loop stays the fallback and the A/B control. Flip RIG_ORCHESTRATE=on to exercise the multi-agent path.
ORCHESTRATE_ON = os.getenv("RIG_ORCHESTRATE", "off").lower() in ("1", "on", "true", "yes")

_VERBOSE = os.getenv("RIG_ORCHESTRATE_VERBOSE", "1").lower() in ("1", "on", "true", "yes")


def _log(label: str, msg: str):
    if _VERBOSE:
        print(f"[{time.strftime('%H:%M:%S')}] [{label}] {msg}", flush=True)


def subagent(role_system, task, tools=True, max_steps=8, label=None, verbose=False,
             session=None, model=None, allowed_tools=None, on_step=None):
    """ONE bounded agent: a fresh Session (its own folder) + a fresh TieredMemory seeded with
    `role_system` + one `run_turn`. Isolated context by construction -- two subagents never share a
    working set. Returns the agent's final text.

    role_system  : the agent's charter/persona (later: loaded from skills/<agent>/SKILL.md).
    task         : the user-side input for this agent.
    tools        : True binds the vetted toolset; False binds none.
    allowed_tools : AUTHORITY ENFORCEMENT. None = full set. A set/list of tool names = least-privilege
                   subset; any other call is denied (a read-only Verifier literally cannot write). This
                   is the one genuinely new mechanism -- a Skill binding the tools it is allowed to use.
    session      : reuse a caller's Session if given; otherwise mint an isolated one per agent.
    """
    label = label or "agent"
    sess = session or Session(f"orch-{label}-{uuid.uuid4().hex[:8]}")
    mem = TieredMemory(sess, system=role_system)
    _log(label, "START")
    t0 = time.time()
    text = run_turn(mem, task, tools=tools, max_steps=max_steps, verbose=verbose, model=model,
                    allowed_tools=allowed_tools, on_step=on_step)
    _log(label, f"DONE ({time.time() - t0:.1f}s)")
    return text


def run_sequential(steps):
    """steps: [(role_system, input), ...]. Each step sees the previous step's output appended.
    Returns the list of step outputs. (An 'Arranger of Doers' -- e.g. Intake -> Validate -> Writer.)"""
    outputs, carry = [], ""
    for i, (si, inp) in enumerate(steps):
        prompt = inp + (f"\n\n--- prior step output ---\n{carry}" if carry else "")
        text = subagent(si, prompt, label=f"seq{i}")
        outputs.append(text)
        carry = text
    return outputs


def run_parallel(tasks, max_workers=4, tools=True):
    """tasks: [(role_system, input), ...]. Run concurrently, each in its OWN subagent; outputs
    returned in order. (The boardroom shape: N independent assessors, one barrier.)"""
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(subagent, si, inp, tools=tools, label=f"par{i}")
                   for i, (si, inp) in enumerate(tasks)]
        return [f.result() for f in futures]


def run_loop(role_system, initial_input, done, max_iters=5):
    """Feed a subagent its own output until done(text) is True (or max_iters). (Refine-until-good.)"""
    text = initial_input
    for i in range(max_iters):
        text = subagent(role_system, text, label=f"loop{i}")
        if done(text):
            break
    return text


def run_hybrid(plan, synthesize_si, tools=True):
    """A coordinator: run `plan` (a list of (role_system, input) tasks) in parallel, then synthesise
    the outputs with one more subagent. (Router -> parallel -> synthesise.)"""
    parts = run_parallel(plan, tools=tools)
    joined = "\n\n".join(f"[result {i}]\n{p}" for i, p in enumerate(parts))
    return subagent(synthesize_si, "Synthesise these results into one answer:\n\n" + joined,
                    tools=False, label="synth")


def run_doer_critic(doer_system, critic_system, task, verify_passes, max_iters=3,
                    doer_allowed=None, critic_allowed=None):
    """THE VERIFY LOOP (generator -> critic -> revise) -- the fix for "claimed done, but wasn't".

    A DOER (write authority) acts on `task`. A separate read-only CRITIC then re-reads GROUND TRUTH
    (SAP) and certifies the doer's claim. `verify_passes(critic_text) -> bool` decides if the critic
    is satisfied. If not, the critic's gap report is handed BACK to the doer to fix -- looped, capped
    at max_iters (the loop-breaker with teeth). Nothing is "done" until a tool-grounded read-back
    agrees. The doer and the critic are DIFFERENT agents with DIFFERENT authority: the one who writes
    is not the one who certifies.

    critic_allowed should be a READ-ONLY tool subset, so the critic structurally cannot paper over a
    gap by writing it itself. Returns {ok, iters, doer, verdict, history}.
    """
    work, history = task, []
    for i in range(max_iters):
        doer_text = subagent(doer_system, work, allowed_tools=doer_allowed, label=f"doer{i}")
        verdict = subagent(
            critic_system,
            ("A doer agent reports it completed this task:\n\n"
             f"--- TASK ---\n{task}\n\n--- DOER'S CLAIM ---\n{doer_text}\n\n"
             "Independently VERIFY the claim by READING SAP back (you may only read). For each object "
             "the doer claims, confirm it actually exists with the right data. End your reply with a "
             "single line 'VERDICT: PASS' (every claim verified) or 'VERDICT: FAIL' (any gap, or any "
             "claim you could not verify), followed by the specific gaps."),
            allowed_tools=critic_allowed, label=f"critic{i}")
        history.append({"iter": i, "doer": doer_text, "verdict": verdict})
        if verify_passes(verdict):
            return {"ok": True, "iters": i + 1, "doer": doer_text, "verdict": verdict, "history": history}
        # not satisfied -> hand the gaps back to the doer and loop
        work = (f"{task}\n\n--- A VERIFIER CHECKED YOUR WORK AGAINST SAP AND IT IS NOT COMPLETE ---\n"
                f"{verdict}\n\nFix ONLY the gaps above (do not redo what already exists), then report.")
    return {"ok": False, "iters": max_iters, "doer": history[-1]["doer"],
            "verdict": history[-1]["verdict"], "history": history}


# A read-only least-privilege subset for verifier/reviewer agents (certify by reading SAP back; never
# write). Matches the read-only callables registered in tools.py.
READ_ONLY_TOOLS = ["get_material", "get_bom", "read_pir", "read_production_version", "read_routing",
                   "read_demand", "read_mrp_list", "find_work_center",
                   "read_cost_condition", "search_materials", "list_allowed_values", "find_field"]

# The VERIFIER's least-privilege set: the read-only tools MINUS search_materials. Withholding search is
# deliberate -- it stops the verifier discovering/guessing a material to verify, so its scope can ONLY be
# the material numbers it was handed (the fix for the bicycle-verified-as-a-laptop scope bug). It reads
# specific numbers; it cannot go hunting.
VERIFIER_TOOLS = ["get_material", "get_bom", "read_pir", "read_production_version", "read_routing",
                  "read_demand", "read_mrp_list", "find_work_center",
                  "read_cost_condition", "list_allowed_values", "find_field"]

_VERIFIER_SKILL = _HERE / "skills" / "genesis-verifier" / "SKILL.md"
_CHECKLIST_SKILL = _HERE / "skills" / "genesis-verification-checklist" / "SKILL.md"


def parse_verdict(text):
    """Read the verifier's structured tail: (passed, missing, unverified, verdict_text). `missing` is
    the count of readable, FIXABLE gaps (drives the heal loop); `unverified` is honest unknowns (no read
    tool -- the loop must NOT chase these). Missing counts default to 0 on PASS, else a conservative 1 if
    the verifier FAILed but emitted no parseable GAPS line."""
    v = re.findall(r"VERDICT:\s*(PASS|FAIL)", text or "", re.IGNORECASE)
    passed = bool(v) and v[-1].upper() == "PASS"
    g = re.findall(r"missing\s*=\s*(\d+)\s*,\s*unverified\s*=\s*(\d+)", text or "", re.IGNORECASE)
    if g:
        missing, unverified = int(g[-1][0]), int(g[-1][1])
    else:
        missing, unverified = (0, 0) if passed else (1, 0)   # FAIL with no counts -> assume a fixable gap
    return passed, missing, unverified, (text or "")


def verify_claim(claim_text, anchor=None, label="genesis-verifier", max_steps=14, on_step=None):
    """Run the read-only genesis-verifier over a doer's completion claim. It re-reads SAP (checking the
    SPEC for EACH in-scope material -- a BOM for every HALB, a PIR for every HAWA, routing + PV for every
    made material) and returns (passed, missing, unverified, verdict_text).

    anchor: the AUTHORITATIVE list of material numbers this genesis actually created (extracted from the
    doer's own tool results). The verifier verifies EXACTLY these -- it has no search tool, so it cannot
    wander onto an unrelated product (the fix for the bicycle-verified-as-a-laptop scope bug). If anchor
    is empty AND the claim names no numbers, the verifier returns insufficient (missing=0) and heals
    nothing."""
    system = _VERIFIER_SKILL.read_text(encoding="utf-8")
    # Make the 7-point genesis-verification-checklist EXPLICITLY part of the loop -- especially Check 7
    # (MRP planability: MRPType=PD, controller set, ProcurementType=E for FERT/HALB), the gap that let
    # HALBs be born F and silently vanish from MRP. The render TEMPLATE is inert here (the verifier has
    # no render_card); the verifier applies the CHECK LOGIC and still emits the VERDICT/GAPS tail.
    try:
        system += ("\n\n--- MANDATORY 7-POINT CHECKLIST (apply to EVERY in-scope material) ---\n"
                   + _CHECKLIST_SKILL.read_text(encoding="utf-8"))
    except OSError:
        pass
    scope = ""
    if anchor:
        scope = ("--- IN-SCOPE MATERIALS (authoritative -- verify EXACTLY these, nothing else) ---\n"
                 + ", ".join(str(a) for a in anchor) + "\n\n")
    out = subagent(
        system,
        ("A doer agent reports it completed a genesis/extension task. Verify ONLY the materials in scope "
         "(below) by READING SAP back (you may only read -- you have NO search tool, so do not look for "
         "other materials). For EACH in-scope material run the MANDATORY 7-point checklist: (1) it exists "
         "with the correct type; if FERT/HALB -> (2) a BOM (get_bom) + (3) a routing (read_routing) + "
         "(4) a production version (read_production_version); if bought/HAWA -> (5) a PIR (read_pir) AND "
         "(6) a committed cost condition with rate>0 (read_cost_condition); and for ALL materials "
         "(7) MRP planability via get_material(segments=[\"mrp\"], plant=<plant>) -- reads the MRP view "
         "(A_ProductPlant / to_ProductSupplyPlanning) straight off the PRODUCT MASTER, so it is reliable on "
         "the cloud backend (the plain header read does NOT carry these fields): MRPType must be PD (not "
         "ND/blank), the MRP controller (MRPResponsible) must be non-blank, and every FERT/HALB "
         "ProcurementType MUST be E -- a HALB with "
         "ProcurementType F is a MISSING gap (MRP raises purchase reqs, not planned orders, breaking the "
         "make cascade). Count any check 1-7 failure (incl HALB ProcType=F, FERT/HALB MRPType=ND, blank "
         "controller, rate-0 cost condition) as MISSING (fixable). If NO material numbers are in scope, "
         "return insufficient per your Skill (do not pick a material to verify). Classify each object "
         "CONFIRMED / MISSING / UNVERIFIED and end with the VERDICT + GAPS lines.\n\n"
         + scope + "--- DOER'S CLAIM ---\n" + (claim_text or "")),
        allowed_tools=VERIFIER_TOOLS, label=label, max_steps=max_steps, on_step=on_step)
    return parse_verdict(out)


# How many materials one verifier turn can read back before its accumulated raw read-backs risk the
# model's 128k context. A 150-material tree overflowed at 255k (session ba4a590c) -- so above this we
# CHUNK. Conservative because reads are raw OData (the lens would raise this a lot). Tunable via env.
VERIFY_BATCH = int(os.getenv("VERIFY_BATCH", "12"))


def verify_claim_chunked(claim_text, anchor=None, label="genesis-verifier", on_step=None,
                         batch_size=VERIFY_BATCH):
    """Verify a LARGE anchor set in BATCHES so verification ALWAYS LANDS -- never a context overflow. Each
    batch gets a SHORT synthetic claim + its own material subset (the anchor IS the authoritative scope, so
    the full doer report -- itself huge -- is not re-sent per batch). Aggregates every batch into ONE
    verdict and only concludes when all batches are done. Same return shape as verify_claim:
    (passed, missing, unverified, verdict_text)."""
    anchor = [str(a) for a in (anchor or [])]
    if len(anchor) <= batch_size:                        # small enough -> a single normal pass
        return verify_claim(claim_text, anchor=anchor, label=label, on_step=on_step)
    batches = [anchor[i:i + batch_size] for i in range(0, len(anchor), batch_size)]
    short = ("A doer completed a multi-level genesis (a FERT + HALB sub-assemblies + bought parts; each "
             "made node has its own BOM/routing/production version, each bought part a PIR + cost). Verify "
             "ONLY the in-scope batch below by reading SAP back.")
    all_passed, tot_missing, tot_unver, verdicts = True, 0, 0, []
    for bi, batch in enumerate(batches, 1):
        if on_step:
            try:
                on_step({"kind": "phase", "text": f"verifying batch {bi}/{len(batches)} ({len(batch)} materials)…"})
            except Exception:
                pass
        p, miss, unv, vtext = verify_claim(short, anchor=batch, label=f"{label}-b{bi}", on_step=on_step)
        all_passed = all_passed and p
        tot_missing += (miss or 0)
        tot_unver += (unv or 0)
        verdicts.append(f"— Batch {bi}/{len(batches)} ({len(batch)} mats): "
                        + ("VERIFIED ✓" if p else f"{miss} MISSING") + (f", {unv} unverified" if unv else ""))
    head = (f"VERIFICATION COMPLETE — {len(batches)} batches, {len(anchor)} materials: "
            + ("ALL VERIFIED ✓" if (all_passed and not tot_missing) else
               f"{tot_missing} MISSING" + (f", {tot_unver} unverified" if tot_unver else "")))
    return all_passed, tot_missing, tot_unver, head + "\n" + "\n".join(verdicts)
