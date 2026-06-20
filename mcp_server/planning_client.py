"""planning_client.py -- the rig's bridge to SAP planning (demand + MRP).

D2M runs MRP/demand in a SEPARATE NWRFC process (sap_planning_mcp.py on :8001/sse) so the SAP-licensed
RFC SDK stays isolated. The ADK app reaches it via an SSE McpToolset. The rig has no ADK, so this is a
THIN hand-rolled MCP-over-SSE client: connect to that same server, call the tool, return its JSON.

Two tools, each confirm-gated like every other rig write (preview -> approve -> commit):
  * create_demand(material, plant, quantity, customer)  -- BAPI_SALESORDER_CREATEFROMDAT2
  * run_mrp(material, plant, multi_level, planning_mode) -- BAPI_MATERIAL_PLANNING (the cascade)

If the planning server is down, the tool returns a CLEAR error (never a silent success) so the model
can't hallucinate "demand created" -- the exact failure mode seen in session 2de78243.
"""
import os
import json
import asyncio

PLANNING_MCP_URL = os.getenv("PLANNING_MCP_URL", "http://127.0.0.1:8001/sse")


async def _acall(tool: str, args: dict):
    """Open a fresh SSE session, call one tool, return the CallToolResult."""
    from mcp import ClientSession
    from mcp.client.sse import sse_client
    async with sse_client(PLANNING_MCP_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(tool, args)


def _invoke(tool: str, args: dict) -> str:
    """Synchronous wrapper (the rig's tool loop is sync, run in a worker thread -> asyncio.run is safe).
    Returns the tool's JSON text, or a clear, model-readable error if the server is unreachable."""
    try:
        res = asyncio.run(_acall(tool, args))
    except Exception as e:
        return (f"ERROR: could not reach the planning server at {PLANNING_MCP_URL} "
                f"({type(e).__name__}: {e}). Start it with `python sap_planning_mcp.py` (needs the NWRFC "
                "SDK + .env). Do NOT tell the user the demand/MRP succeeded -- it did not run.")
    # FastMCP serializes a dict return to JSON text content; prefer that, fall back to structuredContent.
    parts = [getattr(c, "text", None) for c in (res.content or [])]
    parts = [p for p in parts if p]
    if parts:
        return "\n".join(parts)
    sc = getattr(res, "structuredContent", None)
    if sc is not None:
        return json.dumps(sc, ensure_ascii=False, indent=2)
    return "(planning server returned no content)"


def create_demand(material: str, plant: str = "1710", quantity: str = "100",
                  customer: str = "USCU_S03", confirm: bool = False) -> str:
    """Create sales-order demand for a material (each call adds a NEW order -> demand accumulates).

    SAFETY GATE: confirm=false (default) only PREVIEWS. Confirm with the user, then call again
    with confirm=true. Runs on the remote NWRFC planning server.
    """
    if not confirm:
        return (f"PREVIEW -- nothing written. Would create sales-order demand for material {material} "
                f"@ plant {plant}: quantity {quantity}, customer {customer}. "
                "Confirm with the user, then call again with confirm=true.")
    return _invoke("create_demand", {"material": str(material), "plant": str(plant),
                                     "quantity": str(quantity), "customer": str(customer)})


def run_mrp(material: str, plant: str = "1710", multi_level: bool = True,
            planning_mode: str = "1", confirm: bool = False) -> str:
    """Run MRP for a material and return the planned cascade (planned orders + purchase reqs per level).

    multi_level=True plans the whole BOM (MD02); False = header only (MD03).
    planning_mode: '1'=adapt (normal), '3'=delete & recreate (demo: rebuilds the full plan each run).
    SAFETY GATE: confirm=false (default) only PREVIEWS. Runs on the remote NWRFC planning server.
    """
    if not confirm:
        scope = "multi-level (MD02, whole BOM)" if multi_level else "single-level (MD03, header only)"
        return (f"PREVIEW -- nothing run. Would run {scope} MRP for material {material} @ plant {plant} "
                f"(planning mode {planning_mode}). Confirm with the user, then call again with confirm=true.")
    return _invoke("run_mrp", {"material": str(material), "plant": str(plant),
                               "multi_level": bool(multi_level), "planning_mode": str(planning_mode)})
