"""FIRST DEMONSTRABLE MULTI-AGENT RUN -- the parallel "board".

Three BOUNDED reviewers, each its own agent (its own role, its own isolated TieredMemory), run
CONCURRENTLY over the same design question; a fourth agent SYNTHESISES their verdicts into one.
This is the doc's "first truthful 'we are multi-agent'" -- a pure orchestration proof:

  * touches the live SAP/RFC layer NOT at all (reviewers run tools=False -> pure reasoning),
  * touches `vector.py`/embeddings NOT at all (so Task #1 is not a blocker),
  * calls only `model_complete` -> Claude on AI Core (no out-of-pocket spend).

Run from CONDA BASE (so the model seam's deps are present):

    $env:MODEL_PROVIDER = "anthropic"
    python run_board.py

Watch the console: you'll see three [par0]/[par1]/[par2] agents all print START before any prints
DONE -- that interleave is the visible proof they ran in parallel, not one after another. Then [synth]
merges them.
"""
import sys
import time

try:                                  # Windows consoles default to cp1252 and choke on model emoji.
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from orchestrate import run_parallel, subagent

# The thing under review (kept self-contained so the demo needs no SAP read).
TASK = (
    "A new finished good 'BRKT-100' (a stamped steel mounting bracket) is being created for plant 1010. "
    "Proposed master data: material type FERT, base unit EA, procurement type 'E' (in-house production), "
    "MRP type PD, lot size EX, no routing yet, no BOM yet, standard cost not set. "
    "Review this proposal from YOUR domain only. Be concise: list concrete risks/gaps and a GO / NO-GO "
    "with one-line justification."
)

# Three BOUNDED reviewers -- each owns exactly one domain (authority = read + veto). This is the
# Agent ⊃ Skill ⊃ Tools pattern; here the 'skill' is inlined as the role prompt (later: SKILL.md).
REVIEWERS = [
    ("You are the MATERIAL-MASTER reviewer. Authority: material-master correctness ONLY (type, units, "
     "basic data, MRP views existence). Do NOT comment on costing or routing. Veto only material-master "
     "defects.", TASK),
    ("You are the PLANNING reviewer. Authority: MRP/planning consistency ONLY (MRP type, lot size, "
     "procurement type coherence, what planning needs that is missing). Do NOT comment on material-master "
     "naming or costing numbers. Veto only planning defects.", TASK),
    ("You are the COSTING reviewer. Authority: cost/valuation readiness ONLY (standard cost, valuation "
     "class implications, what blocks a cost estimate). Do NOT comment on MRP type or units. Veto only "
     "costing defects.", TASK),
]

SYNTH = (
    "You are the CONDUCTOR's synthesiser. You are given three independent domain reviews (material, "
    "planning, costing). Merge them into ONE verdict: (1) a consolidated risk list grouped by domain, "
    "(2) an overall GO / NO-GO that is NO-GO if ANY reviewer vetoed, (3) the ordered next actions to "
    "clear the blockers. Do not invent issues the reviewers did not raise."
)


def main():
    print("=" * 78)
    print("D2M MULTI-AGENT BOARD  --  3 bounded reviewers in PARALLEL, then 1 synthesiser")
    print("=" * 78)

    t0 = time.time()
    reviews = run_parallel(REVIEWERS, tools=False)   # <-- the multi-agent moment (concurrent subagents)
    t_parallel = time.time() - t0

    domains = ["MATERIAL", "PLANNING", "COSTING"]
    for name, text in zip(domains, reviews):
        print("\n" + "-" * 78)
        print(f"[{name} reviewer]")
        print("-" * 78)
        print(text.strip())

    merged_input = "\n\n".join(f"=== {d} REVIEW ===\n{r}" for d, r in zip(domains, reviews))
    verdict = subagent(SYNTH, merged_input, tools=False, label="synth")

    print("\n" + "=" * 78)
    print("[CONDUCTOR -- synthesised verdict]")
    print("=" * 78)
    print(verdict.strip())

    print("\n" + "=" * 78)
    print(f"3 reviewers ran concurrently in {t_parallel:.1f}s (wall-clock = slowest reviewer, "
          f"not the sum). Total incl. synthesis: {time.time() - t0:.1f}s.")
    print("That parallel interleave is the proof: this is multi-agent, not one loop.")
    print("=" * 78)


if __name__ == "__main__":
    main()
