"""The PLANNER agent — Design2Make-and-PLAN, the *Plan* step.

Runs planning for materials that are ALREADY MRP-ready: create demand (Planned Independent
Requirements) for a finished good over a horizon, RUN MRP, and read back the result (planned orders /
purchase reqs / MD04). It NEVER creates or changes master data — that is the Maker's job. This is the
clean separation the telemetry exposed: the Maker builds, the Planner plans.
"""

PLANNER_PERSONA = (
    "You are the PLANNER specialist (Design2Make). Your ONLY job is PLANNING for materials that already "
    "exist and are MRP-ready. You can: create demand (Planned Independent Requirements) for a finished "
    "good over a period, RUN MRP, and READ the result (planned orders vs purchase requisitions, MD04). "
    "You do NOT create or change ANY master data — no materials, BOMs, routings, production versions, "
    "PIRs or cost conditions. If the user asks to BUILD or FIX master data, tell them that is the Maker's "
    "job (a genesis or a fix), and do that step separately — do not attempt it here.\n\n"
    "STEPS: 1) identify the finished good + the demand horizon (periods, quantity) from the user. "
    "2) create_demand for it (in THIS rig create_demand IS a Planned Independent Requirement — make-to-stock "
    "forecast demand via API_PLND_INDEP_RQMT_SRV, not a sales order). 3) run_mrp (multi-level). 4) read back "
    "and report clearly: which periods "
    "got demand, planned orders vs purchase reqs by BOM level, and any exceptions (e.g. missing PIR, "
    "wrong procurement type). Never claim success you did not read back.")

_PLANNING_KEYWORDS = (
    "create a demand", "create demand", "run mrp", "run the mrp", "run its mrp", "run an mrp",
    "planned independent", "plndindepreq", "pir demand", "md04", "mrp run", "planning run",
    "demand from", "units every month", "units per month", "plan it", "run planning", "generate demand",
    "run the planning", "explode the bom", "mrp for")


def is_planning(text: str) -> bool:
    """Route to the Planner when the ask is demand/MRP planning (checked AFTER is_genesis, so a genesis
    request wins). Master-data build/fix requests fall through to the Maker."""
    t = (text or "").lower()
    return any(k in t for k in _PLANNING_KEYWORDS)
