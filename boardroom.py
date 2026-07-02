"""THE BOARDROOM — a cross-functional panel of bounded PERSONAS that review a master-data proposal, each
from ONE function only, composed by a Chair into a single board decision.

This is the `parallel` + `hybrid` shapes from STARTING_POINT.md applied to review: N independent
function reviewers run CONCURRENTLY (the boardroom), then a Chair (synthesizer) merges their verdicts.
Pairs with the verify→heal LOOP (the critic) already in production — the loop certifies *that the work
landed*; the boardroom judges *whether the work is a good idea* across functions before/at commit.

AUTHORITY: every board member has **READ + ADVISE / VETO** only — it reviews and recommends, it NEVER
writes (it binds no write tools). One domain each. The Chair only synthesizes. The human gate is unchanged.

    convene_board(proposal) -> {"members", "reviews": {func: text}, "verdict": board_decision}

Each persona is a bounded agent (its own isolated memory via subagent). To add a function, add one entry
to PERSONAS — that is the whole "Nth agent" cost.
"""
from concurrent.futures import ThreadPoolExecutor

from orchestrate import run_parallel, subagent   # noqa: F401  (run_parallel kept for ad-hoc use)


def _verdict_of(text: str) -> str:
    """Pull a member's GO / NO-GO off the tail of its review (for a compact activity line)."""
    import re
    m = re.findall(r"VERDICT:\s*(NO-GO|GO)", text or "", re.IGNORECASE)
    return m[-1].upper() if m else "?"

# ---- the functional personas (Agent ⊃ Skill: each charter is the agent's skill, inlined) -------------
# Every charter: ONE function, the lens it judges by, "you do NOT write", end with a GO / NO-GO + concerns.
_VERDICT_RULE = (
    " Review the proposal from YOUR FUNCTION ONLY — stay in your lane; do not comment on other functions. "
    "You have READ + ADVISE authority: you recommend and may VETO, but you never create or change anything. "
    "Be concrete and terse: list the specific risks/gaps you see, then end with a single line "
    "'VERDICT: GO' or 'VERDICT: NO-GO' and a one-sentence justification.")

PERSONAS = {
    "Engineering": (
        "🔧", "You are the ENGINEERING board member (design & manufacturability). Judge the BOM structure "
        "(multi-level correctness: every made sub-assembly has its own BOM), routings/operations, work "
        "centers, units of measure, and whether the assembly can actually be built as specified. Flag "
        "missing sub-assembly BOMs/routings, wrong make-vs-buy typing (FERT/HALB/HAWA), and structural gaps."
        + _VERDICT_RULE),
    "Procurement": (
        "🛒", "You are the PROCUREMENT board member (sourcing). Judge the BOUGHT (HAWA) components: does "
        "each have a supplier, a Purchase Info Record, a committed (non-placeholder) price, and a sane lead "
        "time? Is make-vs-buy right? Flag missing PIRs, $0.01 placeholder prices, single-sourcing risk, and "
        "any bought part with no vendor." + _VERDICT_RULE),
    "Compliance": (
        "📋", "You are the COMPLIANCE / GOVERNANCE board member. Judge data governance & regulatory "
        "fields: CountryOfOrigin set, product/commodity classification, grounded coded values (no guessed "
        "fields), and completeness of mandatory master-data attributes. Flag blank CountryOfOrigin, "
        "ungrounded codes, and any field that would fail an audit." + _VERDICT_RULE),
    "Finance": (
        "💰", "You are the FINANCE / CONTROLLING board member. Judge valuation & cost: valuation class per "
        "material type, standard price set, the cost estimate's ability to roll up (BOM + routing present), "
        "and price control. Flag a FERT/HALB with no released standard cost, missing valuation class, and "
        "any setup that posts goods movements at $0." + _VERDICT_RULE),
    "Planning": (
        "🏭", "You are the PLANNING / SUPPLY-CHAIN board member. Judge plannability: MRP type + controller, "
        "lot-sizing, procurement type coherence, and a production version binding BOM (+ routing) for every "
        "made material so MRP can explode it. Flag MRP types with no controller, made materials with no "
        "production version, and anything that makes MRP inert." + _VERDICT_RULE),
}

CHAIR = (
    "You are the BOARD CHAIR (the Conductor). You are given independent reviews from several functions "
    "(Engineering, Procurement, Compliance, Finance, Planning), each ending in GO / NO-GO. Merge them into "
    "ONE board decision: (1) a consolidated risk register grouped by function; (2) the OVERALL verdict — "
    "**NO-GO if ANY function vetoed** (name which); (3) the ordered actions to clear the blockers, each "
    "tagged with the owning function. Do not invent issues no member raised. End with a single line "
    "'BOARD: GO' or 'BOARD: NO-GO'.")


def convene_board(proposal: str, members=None, tools=False, on_member=None):
    """Run the boardroom over `proposal`: each function reviews CONCURRENTLY, then the Chair synthesises
    one decision. members: subset of PERSONAS (default all). tools=False => pure-reasoning review over the
    proposal text; pass True to let members bind read tools (still no writes).

    on_member(func, phase, text): optional callback fired as each function STARTS ("start", None) and
    finishes ("done", review_text) and when the Chair decides ("chair","start"/"done", verdict) -- so a UI
    can stream the board live. Returns {"members", "reviews": {func: text}, "verdict": board_decision}."""
    members = list(members or PERSONAS.keys())

    from model_client import turn_usage as _tu       # TELEMETRY: per-member token accounting

    def _review(m):
        if on_member:
            on_member(m, "start", None)
        r = subagent(f"{PERSONAS[m][0]} {PERSONAS[m][1]}", proposal, tools=tools, label=f"board-{m}")
        u = _tu()                                    # this member's tokens (run_turn reset at start, own thread)
        if on_member:
            on_member(m, "done", r)
        return r, u

    with ThreadPoolExecutor(max_workers=max(1, len(members))) as ex:
        results = list(ex.map(_review, members))
    reviews = [r for r, _ in results]
    usage = {m: u for m, (_, u) in zip(members, results)}

    joined = "\n\n".join(f"### {m} review\n{r}" for m, r in zip(members, reviews))
    if on_member:
        on_member("Chair", "start", None)
    verdict = subagent(CHAIR, "Merge these function reviews into ONE board decision:\n\n" + joined,
                       tools=False, label="board-chair")
    usage["Chair"] = _tu()
    if on_member:
        on_member("Chair", "done", verdict)
    return {"members": members, "reviews": dict(zip(members, reviews)), "verdict": verdict, "usage": usage}
