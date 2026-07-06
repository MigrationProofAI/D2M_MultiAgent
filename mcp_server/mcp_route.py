"""mcp_route.py — route the rig's SAP tool calls through the CLOUD MCP fleet instead of in-process OData.

Goal: the rig stops being an OData client and becomes a pure MCP client to the d2m-cf servers, so the
local OData wrappers (sap.py/make.py) and the local :8001-:8004 servers can be retired — every SAP call
goes through an mcp-* server only.

SAFETY: flag-gated by SAP_VIA_MCP (default OFF). OFF  -> the rig uses its in-process sap.py/make.py
exactly as today (demo-safe; nothing changes). ON -> each MAPPED tool is dispatched to its cloud server.
This lets us flip ONE object at a time and parity-test it before trusting it.

STATUS: foundation + the MATERIAL object wired. NOT yet live-verified end-to-end (needs the CF apps + the
SAP appliance reachable; the CAL license was down at authoring time). Per-object arg adapters are marked
VERIFY where the cloud tool's exact parameter name needs confirming against the deployed server. Cloud
tools return their own text (no @@DATA@@ cards yet) — the card rendering + the verifier's created-material
anchor parse the in-process format, so re-confirm those per object before flipping the flag in production.
"""
import os
import re
import asyncio

VIA_MCP = os.getenv("SAP_VIA_MCP", "off").strip().lower() in ("1", "on", "true", "yes")

# CF route pattern: https://<app>.<domain>/<path>. All overridable per-server via env (the deploy sets the
# real routes); defaults follow the d2m-cf naming on the hackathon landscape.
_CF = os.getenv("CF_DOMAIN", "cfapps.us10.hana.ondemand.com")


def _u(app, path="/mcp"):
    return f"https://{app}.{_CF}{path}"


# logical server -> (url, transport). OData fleet = streamable-http (/mcp); RFC fleet = SSE (/sse).
# Pointing these at the CF routes (the defaults) is what RETIRES the local :8001-:8004 — once the rig
# talks to these, the local servers are no longer started.
SERVERS = {
    "material": (os.getenv("MATERIAL_MCP_URL", _u("mcp-material")), "http"),
    "bom":      (os.getenv("BOM_MCP_URL",      _u("mcp-bom")),      "http"),
    "routing":  (os.getenv("ROUTING_MCP_URL",  _u("mcp-routing")),  "http"),
    "pir":      (os.getenv("PIR_MCP_URL",       _u("mcp-pir")),       "http"),
    "cost":     (os.getenv("COSTCOND_MCP_URL", _u("mcp-costcond")), "http"),
    "demand":   (os.getenv("DEMAND_MCP_URL",   _u("mcp-plndindepreqmt")), "http"),   # canonical, not mcp-demand
    "mrp":      (os.getenv("MRPVIEW_MCP_URL",  _u("mcp-mrp")),      "http"),
    "planning": (os.getenv("PLANNING_MCP_URL", _u("sap-planning-mcp", "/sse")), "sse"),   # RFC: MRP run
    "prodver":  (os.getenv("PRODVER_MCP_URL",  _u("sap-prodvers-mcp", "/sse")), "sse"),   # RFC: prod version
    "config":   (os.getenv("CONFIG_GRAPH_MCP_URL", _u("mcp-config-graph", "/sse")), "sse"),  # codebook + plant config
}


def server_for(tool: str):
    """TELEMETRY: the cloud MCP server a rig tool routes to (e.g. 'mcp-material', 'sap-planning-mcp'),
    or None if the rig is in-process (SAP_VIA_MCP off) or the tool isn't cloud-routed. Derived from the
    SERVERS URL host so it always matches the deployed name. (ROUTES is resolved lazily at call time.)"""
    import re
    if not VIA_MCP:
        return None
    # tools that route via planning_client/genesis (not ROUTES) -> their cloud server, by name
    _EXTRA = {"run_mrp": "sap-planning-mcp", "create_demand": "mcp-plndindepreqmt",
              "read_demand": "mcp-plndindepreqmt", "read_mrp_list": "mcp-mrp",
              "read_mrp_material": "mcp-mrp", "create_production_version": "sap-prodvers-mcp"}
    if tool in _EXTRA:
        return _EXTRA[tool]
    r = ROUTES.get(tool)
    if not r:
        return None
    url = SERVERS.get(r[0], ("",))[0]
    m = re.match(r"https?://([^./]+)", url)
    return m.group(1) if m else r[0]


async def _acall(url, transport, tool, args):
    from mcp import ClientSession
    if transport == "sse":
        from mcp.client.sse import sse_client
        async with sse_client(url, timeout=10, sse_read_timeout=75) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                return await s.call_tool(tool, args)
    from mcp.client.streamable_http import streamablehttp_client
    import datetime as _dt
    async with streamablehttp_client(url, timeout=_dt.timedelta(seconds=15),
                                     sse_read_timeout=_dt.timedelta(seconds=75)) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return await s.call_tool(tool, args)


def _text(res):
    parts = [getattr(c, "text", None) for c in (res.content or [])]
    parts = [p for p in parts if p]
    return "\n".join(parts) if parts else "(mcp: no content)"


import threading as _thr
_mcp_tl = _thr.local()


def _note_call(name):                                # TELEMETRY: count cloud MCP calls per server (per thread)
    d = getattr(_mcp_tl, "c", None)
    if d is None:
        d = {}; _mcp_tl.c = d
    d[name] = d.get(name, 0) + 1


def turn_mcp_calls(reset=False):
    """Per-server cloud-call counts on THIS thread since last reset (e.g. {'mcp-material': 14, ...}).
    Surfaces the MCP servers hit INSIDE run_genesis (which the agent-tool tags can't, since the creates
    happen in run_genesis's deterministic code, not as agent tool-steps)."""
    d = dict(getattr(_mcp_tl, "c", None) or {})
    if reset:
        _mcp_tl.c = {}
    return d


def call(server: str, tool: str, args: dict, timeout: float = 90.0) -> str:
    """Call one cloud MCP tool, return its text. HARD-bounded by `timeout` so a stalled/looping cloud
    call can NEVER hang the turn (the bug that froze a full-genesis run). Never raises -- a clear ERROR
    string instead, so the agent can see the failure and recover (a down server isn't mistaken for success)."""
    url, transport = SERVERS[server]
    import re as _re
    _m = _re.match(r"https?://([^./]+)", url); _note_call(_m.group(1) if _m else server)
    try:
        return _text(asyncio.run(asyncio.wait_for(_acall(url, transport, tool, args), timeout)))
    except Exception as e:
        kind = "timed out" if isinstance(e, asyncio.TimeoutError) else "failed"
        return (f"ERROR: cloud MCP call {server}.{tool} {kind} ({type(e).__name__}: {e}). "
                f"URL {url}. SAP_VIA_MCP is ON -- check the CF route / that the app is up.")


# ---- the rig-tool -> cloud-tool map (signatures confirmed against d2m-cf) ---------------------------
# Each entry: rig_tool -> (server, cloud_tool, adapt(kwargs)->dict). Adapters send ONLY the cloud tool's
# real parameters (an extra/None arg makes FastMCP reject the call), so each whitelists its keys.
def _pick(kw, *keys):
    return {k: kw[k] for k in keys if k in kw and kw[k] is not None}


def _mat_get(kw):       # rig get_material(material_id) -> mcp-material.read_material(material)
    return {"material": kw.get("material_id") or kw.get("material")}


def _mat_update(kw):    # rig update_material(material_id, fields) -> change_material PATCH on the header
    return {"entity": "A_Product", "keys": {"Product": kw.get("material_id")},
            "fields": kw.get("fields"), "operation": "update", "confirm": bool(kw.get("confirm"))}


_CHANGE = ("entity", "keys", "fields", "operation", "confirm")   # all change_* tools share this shape

ROUTES = {
    # ----- MATERIAL (mcp-material) -----
    # create_material: the cloud's own create_material rebuilds the payload from high-level args, which
    # would DROP the rig's grounded build_material_payload deep-insert. Instead route it through the
    # cloud's generic change_material with operation="add" -> POST the rig's `fields` straight to
    # A_Product (identical to the in-process create; the new Product echoes back for the verifier anchor).
    "create_material":   ("material", "change_material", lambda kw: {"entity": "A_Product", "keys": {}, "fields": kw.get("fields"), "operation": "add", "confirm": bool(kw.get("confirm"))}),
    "get_material":      ("material", "read_material",   _mat_get),
    "search_materials":  ("material", "search_material", lambda kw: _pick(kw, "product", "description", "brand", "product_type", "product_group", "country_of_origin", "plant", "country", "sales_org", "distribution_channel", "language", "top")),
    "update_material":   ("material", "change_material", _mat_update),
    "change_material":   ("material", "change_material", lambda kw: _pick(kw, *_CHANGE)),
    "extend_to_plant":   ("material", "extend_to_plant", lambda kw: _pick(kw, "material", "plant", "product_type", "mrp_type", "procurement_type", "valuation_class", "standard_price", "currency", "confirm")),
    # ----- BOM (mcp-bom) -- add_/remove_bom_component EXCLUDED: rig resolvers (next-item-no); use change_bom -----
    "get_bom":           ("bom", "get_bom",     lambda kw: _pick(kw, "material", "plant", "alternative")),
    "create_bom":        ("bom", "create_bom",  lambda kw: _pick(kw, "material", "plant", "components", "bom_usage", "alternative", "base_quantity", "base_unit", "confirm")),
    "change_bom":        ("bom", "change_bom",  lambda kw: _pick(kw, *_CHANGE)),
    "add_bom_component":    ("bom", "add_component",    lambda kw: _pick(kw, "material", "plant", "component", "alternative", "quantity", "unit", "item_category", "confirm")),
    "remove_bom_component": ("bom", "remove_component", lambda kw: _pick(kw, "material", "plant", "component", "alternative", "confirm")),
    # ----- ROUTING (mcp-routing) -- set_routing_operation EXCLUDED (rig resolver); read_routing stays RFC -----
    "get_routing":       ("routing", "get_routing",      lambda kw: _pick(kw, "material", "plant")),
    "create_routing":    ("routing", "create_routing",   lambda kw: _pick(kw, "material", "plant", "operations", "description", "confirm")),
    "change_routing":    ("routing", "change_routing",   lambda kw: _pick(kw, *_CHANGE)),
    "find_work_center":  ("routing", "find_work_center", lambda kw: _pick(kw, "query", "plant")),
    # read_routing's RFC server (sap-prodvers-mcp) has no read tool on CF -> verify routing via the OData
    # mcp-routing get_routing instead (returns the material's routing assignment = group/counter -> exists).
    "read_routing":      ("routing", "get_routing",      lambda kw: _pick(kw, "material", "plant")),
    # CC added read_production_version to mcp-routing (MKAL read) -> PV now verifies on cloud (S1 done).
    "read_production_version": ("routing", "read_production_version", lambda kw: _pick(kw, "material", "plant")),
    # ----- PIR (mcp-pir) -- set_supplier_terms EXCLUDED (rig resolver) -----
    "read_pir":          ("pir", "read_pir",            lambda kw: _pick(kw, "material", "supplier")),
    "create_info_record":("pir", "create_info_record",  lambda kw: _pick(kw, "material", "supplier", "purchasing_org", "purchasing_group", "currency", "net_price", "lead_time_days", "min_order_qty", "confirm")),
    "change_pir":        ("pir", "change_pir",          lambda kw: _pick(kw, *_CHANGE)),
    # ----- COST CONDITION (mcp-costcond) -- set_condition_price EXCLUDED (rig resolver); price_breaks dropped (no cloud scales) -----
    "read_cost_condition":  ("cost", "read_cost_condition",   lambda kw: _pick(kw, "material", "supplier", "condition_record")),
    "create_cost_condition":("cost", "create_cost_condition", lambda kw: _pick(kw, "material", "supplier", "price", "purchasing_org", "currency", "condition_type", "confirm")),
    "change_cost_condition":("cost", "change_cost_condition", lambda kw: _pick(kw, *_CHANGE)),
    # ----- CONFIG / CODEBOOK GROUNDING (mcp-config-graph, SSE) -- find_field stays in-process (no cloud tool) -----
    "list_allowed_values":          ("config", "list_allowed_values",          lambda kw: _pick(kw, "field")),
    "get_valid_storage_locations":  ("config", "get_valid_storage_locations",  lambda kw: _pick(kw, "plant")),
    "get_valid_mrp_controllers":    ("config", "get_valid_mrp_controllers",    lambda kw: _pick(kw, "plant")),
    "refresh_relationship":         ("config", "refresh_relationship",         lambda kw: _pick(kw, "relationship", "plant")),
    # ----- DEMAND / MRP-read / RFC (run_mrp, prod-version) are ALREADY MCP bridges (planning_client.py /
    #       genesis.py). They are NOT routed here -- instead those modules point at the CF URLs in SERVERS
    #       when SAP_VIA_MCP is on, which is what retires the local :8001/:8002/:8003/:8004. -----
    # STILL IN-PROCESS (no 1:1 cloud tool): create_material, build_material_payload, search_materials,
    #   add_/remove_bom_component, set_routing_operation, set_supplier_terms, set_condition_price,
    #   and the config/codebook grounding tools (list_allowed_values, find_field, get_valid_*).
}


# The cloud create (change_material 'add') truncates its echo, so the new material number can appear ONLY
# in the __metadata id (A_Product('NNNNN')), not as a "Product":"..." field. The rig's verifier anchor and
# genesis._new_matnr both regex "Product":"(\w+)" -- so normalize the response to guarantee that token,
# else genesis aborts at the first create and verification has no scope. (Found in the 12256 write test.)
def _extract_matnr(res):
    s = str(res)
    m = re.search(r'"Product"\s*:\s*"(\w+)"', s) or re.search(r"A_Product\('(\w+)'\)", s)
    return m.group(1) if m else None


def _norm_create(res):
    mat = _extract_matnr(res)
    if mat and ('"Product":"%s"' % mat) not in str(res)[:170]:
        return f'Created material "Product":"{mat}". {res}'
    return res


def _wrap(server, ctool, adapt, post=None):
    def _routed(**kwargs):
        out = call(server, ctool, adapt(kwargs) if adapt else kwargs)
        return post(out) if post else out
    return _routed


def apply(tools: dict) -> dict:
    """Return TOOLS with mapped tools re-pointed at the cloud fleet -- a NO-OP unless SAP_VIA_MCP is on.
    Specs (the agent-facing contract) are preserved; only the implementation changes."""
    if not VIA_MCP:
        return tools
    out = dict(tools)
    for name, (server, ctool, adapt) in ROUTES.items():
        if name in out:
            _fn, spec = out[name]
            if name == "create_material":
                # the guarded shim (B3): create + verify/re-issue the plant view, one path for the
                # registry tool AND genesis's direct rebinding -- the seam cannot drift apart again.
                out[name] = ((lambda **kw: s_create_material(kw.get("fields"), bool(kw.get("confirm")))), spec)
                continue
            out[name] = (_wrap(server, ctool, adapt, None), spec)
    return out


# ============================================================================================
# GENESIS shims -- genesis.py calls sap.py/make.py DIRECTLY (positional args), not via the tool
# registry, so apply() doesn't reach it. These signature-matched shims let genesis.py rebind its
# imported names to cloud calls when VIA_MCP (still confirm-gated; preview returns the cloud preview).
# ============================================================================================
def _svc_server(service):
    s = (service or "API_PRODUCT_SRV").upper()
    for key, srv in (("API_INFORECORD_PROCESS_SRV", "pir"), ("API_PURGPRCGCONDITIONRECORD_SRV", "cost"),
                     ("API_BILL_OF_MATERIAL_SRV", "bom"), ("API_PRODUCTION_ROUTING", "routing"),
                     ("API_PRODUCT_SRV", "material")):
        if s.startswith(key):
            return srv
    return "material"


_CHANGE_TOOL = {"material": "change_material", "pir": "change_pir", "cost": "change_cost_condition",
                "bom": "change_bom", "routing": "change_routing"}


def s_get_material(material, full=False):
    return call("material", "read_material", {"material": str(material)})


def _plant_view_of(fields):
    """(plant, mrp_type, procurement_type) the payload's to_Plant deep-insert intends, or (None, ..)."""
    try:
        row = ((fields or {}).get("to_Plant") or {}).get("results") or []
        row = row[0] if row else {}
        return (str(row.get("Plant") or "") or None,
                str(row.get("MRPType") or "PD"), row.get("ProcurementType"))
    except Exception:
        return None, "PD", None


def _ensure_cloud_plant_view(res, fields):
    """B3 GUARD -- the plant-extension wiring the CF route can silently drop. The cloud
    change_material(add) is NOT yet live-verified to deep-insert the nested to_Plant/to_Valuation
    (module STATUS above): if it only POSTs the A_Product header, every CF-created material is born
    MARA-basic-only -- the regression. So after a create whose payload INTENDED a plant view, read the
    material back; unless the read positively shows that plant's view, re-issue extend_to_plant
    explicitly (idempotent-safe: an 'already exists' rejection means the view was there)."""
    mat = _extract_matnr(res)
    plant, mrp_type, proc = _plant_view_of(fields)
    if not mat or not plant:
        return res
    back = call("material", "read_material", {"material": mat})
    canon = re.sub(r"\s+", "", str(back)).replace("'", '"')
    if f'"Plant":"{plant}"' in canon:
        return res                                    # deep-insert confirmed -- the view landed
    ext = s_extend_to_plant(mat, plant, product_type=str((fields or {}).get("ProductType") or "ROH"),
                            mrp_type=mrp_type, procurement_type=proc, confirm=True)
    if re.search(r"already exist|duplicate", str(ext), re.I):
        note = f"[plant view @{plant}: present (extend reported already-exists)]"
    elif re.search(r"error|failed", str(ext), re.I):
        note = f"[⚠ plant view @{plant} NOT confirmed: create echo lacked it and extend_to_plant failed -- {str(ext)[:160]}]"
    else:
        note = f"[plant view @{plant}: re-issued via extend_to_plant (cloud add did not deep-insert it)]"
    return f"{res}\n{note}"


def s_create_material(fields, confirm=False):   # grounded deep-insert -> cloud change_material add
    res = _norm_create(call("material", "change_material",
                {"entity": "A_Product", "keys": {}, "fields": fields, "operation": "add", "confirm": bool(confirm)}))
    if confirm:
        try:
            res = _ensure_cloud_plant_view(res, fields)
        except Exception:
            pass
    return res


def s_extend_to_plant(material, plant, product_type="ROH", mrp_type="ND", procurement_type=None,
                      valuation_class=None, standard_price=100.0, currency=None, confirm=False):
    a = {"material": str(material), "plant": str(plant), "product_type": product_type,
         "mrp_type": mrp_type, "standard_price": standard_price, "confirm": bool(confirm)}
    if procurement_type:
        a["procurement_type"] = procurement_type
    if valuation_class:
        a["valuation_class"] = valuation_class
    if currency:
        a["currency"] = currency
    return call("material", "extend_to_plant", a)


def s_change_material_view(entity, keys, fields=None, operation="update", service=None, confirm=False):
    server = _svc_server(service)
    return call(server, _CHANGE_TOOL[server],
                {"entity": entity, "keys": keys, "fields": fields or {}, "operation": operation, "confirm": bool(confirm)})


def s_create_bom(material, plant, components, confirm=False, **k):
    return call("bom", "create_bom",
                {"material": str(material), "plant": str(plant), "components": components, "confirm": bool(confirm)})


def s_create_routing(material, plant, operations, description="", confirm=False, **k):
    return call("routing", "create_routing",
                {"material": str(material), "plant": str(plant), "operations": operations,
                 "description": description, "confirm": bool(confirm)})


def s_create_info_record(material, supplier, purchasing_org=None, purchasing_group=None, currency=None,
                         net_price=0.01, lead_time_days=10, min_order_qty=1,
                         supplier_material_number=None, confirm=False, **k):
    a = {"material": str(material), "supplier": str(supplier), "net_price": net_price,
         "lead_time_days": lead_time_days, "min_order_qty": min_order_qty, "confirm": bool(confirm)}
    for key, val in (("purchasing_org", purchasing_org), ("purchasing_group", purchasing_group), ("currency", currency)):
        if val:
            a[key] = val
    return call("pir", "create_info_record", a)


def s_create_cost_condition(material, supplier, price, purchasing_org=None, currency=None,
                            price_breaks=None, condition_type="PPR0", confirm=False, **k):
    a = {"material": str(material), "supplier": str(supplier), "price": price,
         "condition_type": condition_type, "confirm": bool(confirm)}
    for key, val in (("purchasing_org", purchasing_org), ("currency", currency)):
        if val:
            a[key] = val
    return call("cost", "create_cost_condition", a)   # NOTE cloud has no scales; price_breaks dropped
