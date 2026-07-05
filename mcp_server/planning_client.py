"""planning_client.py -- the rig's bridge to SAP planning (demand + MRP).

Two separate SAP back ends, reached over MCP so the rig itself holds no SAP SDK:

  * DEMAND  -> mcp-plndindepreqmt (jl-recon/d2m-cf/mcp-plndindepreqmt) on :8003, streamable-http. PROPER
    forecast demand: Planned Independent Requirements (API_PLND_INDEP_RQMT_SRV, type VSF / version 00) --
    the make-to-stock signal MRP consumes. This REPLACED the old sales-order (BAPI_SALESORDER_CREATEFROMDAT2)
    demand, which created sold-to orders that accumulated -- the wrong object for a forecast-driven build.
    (Tools on that server: create/read/change_plndindepreqmt; the rig keeps the agent verb `create_demand`.)
  * MRP     -> sap_planning_mcp.py on :8001/sse (NWRFC). BAPI_MATERIAL_PLANNING -- RUNS the planning.
  * MD04    -> mcp-mrp (jl-recon/d2m-cf/mcp-mrp) on :8004, streamable-http. API_MRP_MATERIALS_SRV_01
    (READ): the MD04 stock/requirements list -- what the run PRODUCED (stock, planned orders, purchase
    requisitions, PIRs, dependent requirements). Read-only; the verification view for an MRP execution.

Each write tool is confirm-gated like every other rig write (preview -> approve -> commit). If a back-end
server is down, the tool returns a CLEAR error (never a silent success) so the model can't hallucinate
"demand created" -- the exact failure mode seen in session 2de78243.
"""
import os
import re
import json
import asyncio

PLANNING_MCP_URL = os.getenv("PLANNING_MCP_URL", "http://127.0.0.1:8001/sse")          # MRP RUN (SSE/NWRFC)
DEMAND_MCP_URL = os.getenv("DEMAND_MCP_URL", "http://127.0.0.1:8003/mcp")              # PIR demand (streamable-http)
MRPVIEW_MCP_URL = os.getenv("MRPVIEW_MCP_URL", "http://127.0.0.1:8004/mcp")            # MD04 read (streamable-http)

# When SAP_VIA_MCP is on, point these at the CLOUD routes (mcp_route.SERVERS) instead of the local
# :8001/:8003/:8004 -- this is what retires the local servers. Explicit *_MCP_URL env still wins.
try:
    import mcp_route as _mr                                                            # noqa: E402
    if _mr.VIA_MCP:
        PLANNING_MCP_URL = os.getenv("PLANNING_MCP_URL") or _mr.SERVERS["planning"][0]
        DEMAND_MCP_URL = os.getenv("DEMAND_MCP_URL") or _mr.SERVERS["demand"][0]
        MRPVIEW_MCP_URL = os.getenv("MRPVIEW_MCP_URL") or _mr.SERVERS["mrp"][0]
except Exception:
    pass


async def _acall(tool: str, args: dict):
    """Open a fresh SSE session (:8001 MRP server), call one tool, return the CallToolResult."""
    from mcp import ClientSession
    from mcp.client.sse import sse_client
    async with sse_client(PLANNING_MCP_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(tool, args)


async def _acall_http(url: str, tool: str, args: dict):
    """Open a fresh streamable-http session (mcp-demand), call one tool, return the CallToolResult."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    async with streamablehttp_client(url) as (read, write, _):          # 3-tuple: +get_session_id
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(tool, args)


def _content(res) -> str:
    """Flatten a CallToolResult to text -- FastMCP returns the tool's string as text content; fall
    back to structuredContent for dict returns."""
    parts = [getattr(c, "text", None) for c in (res.content or [])]
    parts = [p for p in parts if p]
    if parts:
        return "\n".join(parts)
    sc = getattr(res, "structuredContent", None)
    if sc is not None:
        return json.dumps(sc, ensure_ascii=False, indent=2)
    return "(server returned no content)"


def _note(url):                                      # TELEMETRY: count this cloud call under its server
    try:
        import re
        import mcp_route as _mr
        m = re.match(r"https?://([^./]+)", url)
        _mr._note_call(m.group(1) if m else url)
    except Exception:
        pass


def _invoke(tool: str, args: dict) -> str:
    """Synchronous wrapper for the :8001 MRP server (the rig's tool loop is sync, in a worker thread ->
    asyncio.run is safe). Returns the tool's JSON text, or a clear error if the server is unreachable."""
    _note(PLANNING_MCP_URL)
    try:
        res = asyncio.run(_acall(tool, args))
    except Exception as e:
        return (f"ERROR: could not reach the planning server at {PLANNING_MCP_URL} "
                f"({type(e).__name__}: {e}). Start it with `python sap_planning_mcp.py` (needs the NWRFC "
                "SDK + .env). Do NOT tell the user the demand/MRP succeeded -- it did not run.")
    return _content(res)


def _invoke_http(url: str, tool: str, args: dict, down_hint: str) -> str:
    """Synchronous wrapper for the streamable-http mcp-demand server. Returns the tool's text, or a
    clear, model-readable error if the server is unreachable (so the model never claims false success)."""
    _note(url)
    try:
        res = asyncio.run(_acall_http(url, tool, args))
    except Exception as e:
        return (f"ERROR: could not reach the demand server at {url} ({type(e).__name__}: {e}). "
                f"{down_hint} Do NOT tell the user the demand succeeded -- it did not run.")
    return _content(res)


_DEMAND_DOWN = ("Start it with `python run_demand.py` (mcp-plndindepreqmt on :8003, "
                "needs SAP_USER/SAP_PASS).")

_MATNUM = re.compile(r"^\d{4,}$")           # SAP material numbers are numeric (5-digit typical)


def _resolve_material(material: str) -> tuple[str, str]:
    """A planning call needs the material NUMBER, not its description -- SAP rejects a description with
    an opaque 'not defined' error that looks like a plant-enablement gap (it isn't). If `material` isn't
    numeric, resolve it by description via search_materials FIRST, so a call like
    create_demand("FG-PUMP-SKID-001", ...) just works instead of derailing into an unrelated recovery
    loop (session 5fc3f68b: description sent as-is -> 'not defined' -> the model wrongly self-diagnosed
    a plant-enablement problem and spun into enable_plant_production retries).
    Returns (resolved_material, note) -- note is "" when no resolution was needed/attempted."""
    material = str(material).strip()
    if _MATNUM.match(material):
        return material, ""
    try:
        from sap import search_materials
        hits = json.loads(search_materials(description=material, top=5)).get("materials", [])
    except Exception as e:
        return material, f"(could not resolve {material!r} to a material number: {type(e).__name__}: {e})"
    if len(hits) == 1:
        resolved = hits[0]["Product"]
        return resolved, f"(resolved {material!r} -> material {resolved})"
    if not hits:
        return material, f"(no material found matching description {material!r})"
    return material, (f"({len(hits)} materials match {material!r} -- "
                      f"{', '.join(h['Product'] for h in hits[:5])}; pass the exact material number)")


def _months(start: str, end: str) -> list[str]:
    """Inclusive YYYYMM range start..end (e.g. '202607'..'202612' -> the six Jul-Dec buckets).
    Returns [] if either is malformed or end precedes start."""
    try:
        y, m = int(start[:4]), int(start[4:6])
        ey, em = int(end[:4]), int(end[4:6])
    except (ValueError, IndexError):
        return []
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        if len(out) > 60:                                   # safety bound (5 years)
            break
    return out


def create_demand(material: str, plant: str = "1710", quantity: str = "100",
                  period: str = "", period_to: str = "", confirm: bool = False) -> str:
    """Create Planned Independent Requirements (forecast) demand for a make-to-stock finished good --
    type VSF / version 00 via API_PLND_INDEP_RQMT_SRV (mcp-demand on :8003). This is the demand object
    MRP consumes.

    ONE call, one OR many months:
      * single month  -> set `period` (YYYYMM; empty = next month).
      * a RANGE        -> set `period` = START YYYYMM and `period_to` = END YYYYMM; this writes one
        bucket per month of `quantity` each (e.g. period=202607, period_to=202612 -> 30/mo Jul-Dec).
      Do NOT call this tool repeatedly to cover multiple months -- pass the range and it loops for you.

    SAFETY GATE: confirm=false (default) only PREVIEWS. Confirm with the user, then call again with
    confirm=true. Runs on the remote mcp-demand server.
    """
    material, _note = _resolve_material(material)
    if _note and "resolved" not in _note:                      # ambiguous / not-found -- stop here, clearly
        return f"ERROR: {_note}"

    if period_to:
        if not period:
            return ("ERROR: when using period_to (a range) you must also give the START `period` "
                    "(YYYYMM). E.g. period=202607, period_to=202612 for Jul-Dec 2026.")
        periods = _months(period, period_to)
        if not periods:
            return f"ERROR: bad period range {period!r}..{period_to!r} (YYYYMM, and end >= start)."
    else:
        periods = [period]                                  # single; "" -> server defaults to next month

    if not confirm:
        shown = ", ".join(p or "next month" for p in periods)
        return (f"PREVIEW -- nothing written. {_note + ' ' if _note else ''}Would create Planned Independent "
                f"Requirements (forecast) demand for material {material} @ plant {plant}: {quantity} units "
                f"in {len(periods)} period(s) [{shown}], type VSF/00 (API_PLND_INDEP_RQMT_SRV). Confirm "
                "with the user, then call again with confirm=true.")

    results = [(per, _invoke_http(DEMAND_MCP_URL, "create_plndindepreqmt",
                                  {"product": str(material), "plant": str(plant),
                                   "quantity": str(quantity), "period": str(per or ""), "confirm": True},
                                  _DEMAND_DOWN)) for per in periods]
    if len(results) == 1:
        return results[0][1]
    ok = sum(1 for _, r in results if "HTTP 201" in r or "CREATED" in r)
    lines = "\n".join(f"  {per}: {r.splitlines()[0][:120]}" for per, r in results)
    return (f"Created {ok}/{len(results)} monthly PIRs of {quantity} units for {material} @ {plant} "
            f"(type VSF/00):\n{lines}")


def read_demand(material: str, plant: str = "1710") -> str:
    """Read EXISTING Planned Independent Requirements (header + period quantities) for a material --
    so a verifier can confirm the demand actually persisted. Runs on the remote mcp-demand server."""
    return _invoke_http(DEMAND_MCP_URL, "read_plndindepreqmt",
                        {"product": str(material), "plant": str(plant)}, _DEMAND_DOWN)


def run_mrp(material: str, plant: str = "1710", multi_level: bool = True,
            planning_mode: str = "1", confirm: bool = False) -> str:
    """Run MRP for a material and return the planned cascade (planned orders + purchase reqs per level).

    multi_level=True plans the whole BOM (MD02); False = header only (MD03).
    planning_mode: '1'=adapt (normal), '3'=delete & recreate (demo: rebuilds the full plan each run).
    SAFETY GATE: confirm=false (default) only PREVIEWS. Runs on the remote NWRFC planning server.
    """
    material, _note = _resolve_material(material)
    if _note and "resolved" not in _note:                      # ambiguous / not-found -- stop here, clearly
        return f"ERROR: {_note}"

    if not confirm:
        scope = "multi-level (MD02, whole BOM)" if multi_level else "single-level (MD03, header only)"
        return (f"PREVIEW -- nothing run. {_note + ' ' if _note else ''}Would run {scope} MRP for material "
                f"{material} @ plant {plant} (planning mode {planning_mode}). Confirm with the user, "
                "then call again with confirm=true.")
    return _invoke("run_mrp", {"material": str(material), "plant": str(plant),
                               "multi_level": bool(multi_level), "planning_mode": str(planning_mode)})


_MRPVIEW_DOWN = ("Start it with `python run_mrpview.py` (mcp-mrp on :8004, needs SAP_USER/SAP_PASS).")


def read_mrp_list(material: str, plant: str = "1710", area: str = "") -> str:
    """Read the MD04 stock/requirements list for a material -- every supply & demand element the MRP run
    produced: stock, planned orders, purchase requisitions, planned independent requirements, sales
    orders, dependent requirements -- each with date, quantity and running available quantity. This is
    the verification view for an MRP execution. `area` defaults to the plant. Read-only (mcp-mrp :8004)."""
    return _invoke_http(MRPVIEW_MCP_URL, "read_mrp_list",
                        {"material": str(material), "plant": str(plant), "area": str(area or "")},
                        _MRPVIEW_DOWN)


def read_mrp_material(material: str, plant: str = "1710", area: str = "") -> str:
    """Read the MRP material master for a material @ plant: procurement type (E in-house / F external),
    low-level code, base unit, material type/group, MRP area. Read-only (mcp-mrp :8004)."""
    return _invoke_http(MRPVIEW_MCP_URL, "read_mrp_material",
                        {"material": str(material), "plant": str(plant), "area": str(area or "")},
                        _MRPVIEW_DOWN)
