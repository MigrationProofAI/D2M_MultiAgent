"""SAP tools as PLAIN CALLABLES for the rig -- no MCP server, no ADK. We import the proven OData
readers/writers from mcp_server/sap.py (they're decorated with @mcp.tool() but FastMCP returns the
original function, so they import as ordinary callables) and expose the JSON schemas the model needs.

Add a tool by registering it in TOOLS: name -> (callable, openai-tool-spec)."""
import os
import sys
import re
import json
import shutil
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "mcp_server"))
from sap import (get_material, search_materials, create_material, update_material,   # noqa: E402
                 build_material_payload, list_allowed_values, find_field, extend_to_plant,
                 change_material, change_routing, change_pir,            # noqa: E402  -- typed UPDATE/soft-delete
                 change_cost_condition, change_bom)                      # noqa: E402     (one per in-scope object)
from genesis import (run_genesis, enable_plant_production,   # noqa: E402  -- Design2Make orchestration + one-call plant enablement
                     read_production_version, read_routing)  # noqa: E402  -- :8002 RFC reads (MKAL / MAPL)
from make import (get_bom, add_bom_component, remove_bom_component, create_bom,   # noqa: E402  -- post-genesis BOM edits
                  read_pir, create_info_record, create_cost_condition,  # noqa: E402  -- PIR + cost (bought path)
                  find_work_center, get_routing, set_routing_operation,  # noqa: E402  -- routing read + WC repoint
                  set_supplier_terms,                                    # noqa: E402  -- PIR price/lead/min correction
                  read_cost_condition, set_condition_price)              # noqa: E402  -- cost price read + correct
from planning_client import (create_demand, read_demand, run_mrp,   # noqa: E402  -- PIR demand (:8003) + MRP run (:8001)
                             read_mrp_list, read_mrp_material)       # noqa: E402  -- MD04 read (mcp-mrp :8004)
from serper import google_search           # noqa: E402  -- web search for prices / specs
from config_graph import (get_valid_storage_locations, get_valid_mrp_controllers,   # noqa: E402
                          refresh_relationship)        # plant-keyed config (T001L / T024D), not in the codebook


def _spec(name, desc, props, required):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props, "required": required}}}


def load_bom_from_file(path: str, confirm: bool = False, enrich: bool = False, on_step=None) -> str:
    """Drive genesis DETERMINISTICALLY from a tabbed-Excel BOM file (no vision model): parse the
    workbook into a genesis spec, then run the same run_genesis write-chain. confirm=false previews.

    enrich=false (default) uses ONLY the sourcing in the file -- lossless, reproducible, ~0 tokens (this is
    what scale tests want). enrich=true runs an OPT-IN web-sourcing pass first: for any bought part with a
    BLANK price, it searches the web and fills a real unit price before the preview/commit (the "it found
    the price" behaviour of image genesis, on the lossless file path). Vendor is unchanged. Leave it off to
    keep a run fully deterministic."""
    try:
        from excel_bom import genesis_from_excel                 # mcp_server is on sys.path
    except Exception as e:
        return f"Excel BOM support unavailable (openpyxl missing?): {type(e).__name__}: {e}"
    p = path
    if not os.path.exists(p):                                    # allow a bare filename next to the rig
        alt = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
        if os.path.exists(alt):
            p = alt
        else:
            return (f"BOM file not found: {path!r}. Put the .xlsx next to the rig or give a full path. "
                    "Generate one with `python gen_bom_fixture.py --n 50 --out bom_50.xlsx`.")
    try:
        spec, warnings = genesis_from_excel(p)
    except Exception as e:
        return f"Failed to parse Excel BOM {path!r}: {type(e).__name__}: {e}"
    enrich_head = ""
    if enrich:
        try:
            from enrichment import enrich_sourcing
            spec, enotes = enrich_sourcing(spec)
            enrich_head = "Web-sourcing (opt-in):\n" + "\n".join(f"  {n}" for n in enotes) + "\n\n"
        except Exception as e:
            enrich_head = f"Web-sourcing skipped ({type(e).__name__}: {e}).\n\n"
    head = ("Parse warnings:\n" + "\n".join(f"  - {w}" for w in warnings) + "\n\n") if warnings else ""
    if not confirm:
        # PREVIEW: a decision-grade PLAN REPORT (deterministic contract + cost + flags), not a raw tree dump.
        # This is what the board reasons on and the user approves; web.py renders the tabbed Genesis Plan card.
        try:
            from plan_report import plan_report
            pr = plan_report(spec, (spec.get("parent") or {}).get("plant") or "1710")
            return enrich_head + head + pr["summary"]
        except Exception as e:
            return enrich_head + head + str(run_genesis(spec, confirm=False)) + f"\n(plan report unavailable: {e})"
    return enrich_head + head + str(run_genesis(spec, confirm=True, on_step=on_step))


def reconcile_routings(bom_file: str, fert: str, plant: str = "1710") -> str:
    """PRE-vs-POST routing reconciliation for a committed file-genesis: for each MADE node, the work centers
    the BOM file PLANNED vs the routing actually CREATED in SAP -- MATCH / DRIFT / MISSING per node, plus the
    work-center coverage (planned vs created). Read-only, deterministic. Renders a Routing Reconciliation card.

    Args:
        bom_file: the .xlsx BOM that was committed (e.g. 'bom_auto_300.xlsx').
        fert: the FERT material number created by that genesis (e.g. '13973'); the tree expands from it.
        plant: plant code (default 1710).
    """
    try:
        from excel_bom import genesis_from_excel
        from conformance import reconcile_routings as _rr
        from plan_card import routing_recon_card
    except Exception as e:
        return f"Routing reconciliation unavailable: {type(e).__name__}: {e}"
    p = bom_file
    for cand in (bom_file, os.path.join(os.path.dirname(os.path.abspath(__file__)), bom_file),
                 os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server", bom_file)):
        if os.path.exists(cand):
            p = cand
            break
    try:
        spec, _ = genesis_from_excel(p)
    except Exception as e:
        return f"Could not parse BOM {bom_file!r}: {type(e).__name__}: {e}"
    res = _rr(spec, [str(fert)], plant)
    card = routing_recon_card(res["data"])
    data_block = "@@DATA@@" + card.split("@@DATA@@", 1)[1] if "@@DATA@@" in card else ""
    return res["report"] + "\n" + data_block


# --- skill tools (Step 3): progressive disclosure. The registry is set per-session by the loop/gate ---
_SKILL_REG = None


def set_skill_registry(reg):
    global _SKILL_REG
    _SKILL_REG = reg


def _load_skill(name):
    return _SKILL_REG.load_body(name) if _SKILL_REG else "ERROR: no skill registry set"


def _run_skill_script(name, script, args=None):
    return _SKILL_REG.run_script(name, script, args) if _SKILL_REG else "ERROR: no skill registry set"


# --- demonstration -> skill loop (write -> promote -> render). The CURRENT session is set per turn by
#     the loop (web.py/main.py) so these tools know which sessions/<id>/assets/ to write into. ---
_CURRENT_SESSION = None


def set_current_session(sess):
    global _CURRENT_SESSION
    _CURRENT_SESSION = sess


def _safe(name, default="skill"):
    return re.sub(r"[^A-Za-z0-9._-]", "-", str(name)).strip("-") or default


def _write_skill_artifact(skill_name, files):
    """Persist a composed skill artifact as REAL files under the CURRENT session's assets/<skill_name>/.
    files = {filename: text}. Nothing durable yet -- the user reviews, then you promote_skill it."""
    if _CURRENT_SESSION is None:
        return "ERROR: no current session (cannot write assets)."
    if not isinstance(files, dict) or not files:
        return "ERROR: files must be a non-empty object {filename: content}."
    safe = _safe(skill_name)
    dest = _CURRENT_SESSION.assets / safe
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    for fn, content in files.items():
        fsafe = _safe(fn, "")
        if not fsafe:
            continue
        (dest / fsafe).write_text(str(content), encoding="utf-8")
        written.append(fsafe)
    return (f"Wrote {len(written)} file(s) to sessions/{_CURRENT_SESSION.id}/assets/{safe}/: "
            f"{', '.join(written)}. Review them, then -- with my explicit approval -- promote_skill('{safe}', "
            f"...) to make it durable + triggerable.")


def _skill_md(safe, description, when_to_trigger, src_dir):
    """Compose the durable SKILL.md: frontmatter + the invoke recipe + the artifact files EMBEDDED, so
    load_skill(name) hands the agent the schema/mapping/template in one shot."""
    parts = [
        "---",
        f"name: {safe}",
        f"description: {description or ('Render the ' + safe + ' card from live SAP data')}",
        f"when_to_trigger: {when_to_trigger or 'when the user asks for this card, or after a related run_mrp()'}",
        "---",
        "",
        f"# {safe}",
        "",
        "Render a card from LIVE SAP data into the STRUCTURED-DATA panel (not just chat). The runtime does",
        "NOT execute inline scripts, so YOU bind the data and the rendering goes through render_card.",
        "",
        "## Invoke recipe",
        "1. Call the sources named in MAPPING (run_mrp / get_material / get_bom) for the material + plant in play.",
        "2. Bind the returned data into the SCHEMA shape using the MAPPING rules.",
        "3. Build the card as HTML following the TEMPLATE layout (sections, colours, chips).",
        "4. Call render_card(title=..., content=<the card HTML>). It surfaces in the Structured Data panel.",
        "",
    ]
    for fn in sorted(p.name for p in src_dir.iterdir() if p.is_file()):
        try:
            parts.append(f"## {fn}\n\n{(src_dir / fn).read_text(encoding='utf-8')}\n")
        except Exception:
            continue
    return "\n".join(parts)


def _promote_skill(skill_name, description="", when_to_trigger="", confirm=False):
    """HUMAN-GATED. With the user's explicit approval, copy a reviewed artifact from the session's
    assets/ into the durable skills/<name>/, write SKILL.md (frontmatter + invoke recipe + embedded
    artifact), and refresh the registry so it is indexed + load_skill-able + triggers THIS turn."""
    if _CURRENT_SESSION is None:
        return "ERROR: no current session."
    safe = _safe(skill_name)
    src = _CURRENT_SESSION.assets / safe
    if not src.exists() or not any(src.iterdir()):
        return (f"ERROR: no artifact at sessions/{_CURRENT_SESSION.id}/assets/{safe}/. "
                f"Compose it first with write_skill_artifact('{safe}', {{...}}).")
    from skills import SKILLS_DIR
    files = sorted(p.name for p in src.iterdir() if p.is_file())
    dest = Path(SKILLS_DIR) / safe
    if not confirm:
        return (f"PREVIEW -- nothing promoted (human-gated). Would copy {len(files)} file(s) {files} from "
                f"assets/{safe}/ to skills/{safe}/, write SKILL.md (triggers: {when_to_trigger!r}), and index "
                f"it. After the user approves, call again with confirm=true.")
    dest.mkdir(parents=True, exist_ok=True)
    for p in src.iterdir():
        if p.is_file():
            shutil.copy2(p, dest / p.name)
    (dest / "SKILL.md").write_text(_skill_md(safe, description, when_to_trigger, src), encoding="utf-8")
    refreshed = _SKILL_REG.refresh() if (_SKILL_REG and hasattr(_SKILL_REG, "refresh")) else None
    note = ("now in the skills index, load_skill-able, and triggering THIS turn"
            if refreshed is not None else "registered (restart to index)")
    return (f"PROMOTED '{safe}' -> skills/{safe}/ ({len(files)} artifact file(s) + SKILL.md). It is {note}. "
            f"Triggers: {when_to_trigger or '(set when_to_trigger to control this)'}.")


def _render_card(title="", content="", subtitle=""):
    """Render a model-composed card into the STRUCTURED-DATA panel (not just chat). `content` is the card
    body as HTML or Markdown (e.g. a skill TEMPLATE populated with live data). Rides the @@DATA@@ ->
    _cards forwarder, so web.py surfaces it as a typed card."""
    payload = {"kind": "card", "title": str(title or ""), "subtitle": str(subtitle or ""),
               "content": str(content or "")}
    return (f"Rendered card '{title}' into the Structured Data panel.\n"
            "@@DATA@@" + json.dumps(payload, ensure_ascii=False))


# name -> (callable, OpenAI tool spec). The substance kept from D2M; the ceremony (MCP/ADK) dropped.
TOOLS = {
    "get_material": (get_material, _spec(
        "get_material", "Read a material/product master by ID from SAP S/4HANA. The HEADER holds "
        "CROSS-PLANT fields ONLY — MRPType, ProcurementType, MRP controller, tax, sales, standard price "
        "etc. are NOT header fields; they live on plant/sales/tax/valuation VIEWS. Use `segments` to pull "
        "any view: e.g. segments=['mrp'] for MRPType/ProcurementType/MRPResponsible, ['tax'], ['sales'], "
        "['valuation'] for standard price. Pass `plant` to scope plant views.",
        {"material_id": {"type": "string", "description": "exact material number"},
         "full": {"type": "boolean", "description": "true = all header fields"},
         "segments": {"type": "array", "items": {"type": "string"},
                      "description": "views to include: plant, mrp, workscheduling, storage, sales, tax, "
                                     "valuation (price/cost), procurement, units, description (or a raw to_* nav prop)"},
         "plant": {"type": "string", "description": "filter plant-scoped views to this plant"}},
        ["material_id"])),

    "build_material_payload": (build_material_payload, _spec(
        "build_material_payload",
        "Assemble a verified create payload (returns {fields}). Smart defaults baked in; pass plant for a plant view.",
        {"description": {"type": "string"}, "product_type": {"type": "string", "description": "ROH|HAWA|HALB|FERT"},
         "base_unit": {"type": "string"}, "product_group": {"type": "string"},
         "plant": {"type": "string"}, "sales_org": {"type": "string"}},
        ["description", "product_type", "base_unit", "product_group"])),

    "create_material": (create_material, _spec(
        "create_material", "Create a material in SAP. confirm=false PREVIEWS (no write); confirm=true COMMITS.",
        {"fields": {"type": "object", "description": "the deep-insert fields, e.g. from build_material_payload"},
         "confirm": {"type": "boolean"}}, ["fields"])),

    "search_materials": (search_materials, _spec(
        "search_materials", "Find a material's NUMBER (and details) by attributes — use description= for a "
        "name like 'ASUS ROG Gaming Laptop', product= for a code-like number. The smart entry point for "
        "resolving a name to its material number before a BOM/update.",
        {"product": {"type": "string", "description": "material number, full or partial (code-like)"},
         "description": {"type": "string", "description": "free-text in the material description"},
         "product_type": {"type": "string"}, "plant": {"type": "string"}, "top": {"type": "integer"}}, [])),

    "update_material": (update_material, _spec(
        "update_material", "Change fields on an EXISTING material (PATCH). Use THIS — not create_material — "
        "to set or correct a field (e.g. CountryOfOrigin, ProductGroup) on a material that already exists. "
        "create_material is ONLY for brand-new materials; calling it on an existing one fails or duplicates. "
        "confirm=false PREVIEWS (no write); confirm=true COMMITS.",
        {"material_id": {"type": "string", "description": "the existing material number"},
         "fields": {"type": "object", "description": "{ExactODataFieldName: new_value}, e.g. {\"CountryOfOrigin\":\"US\"}"},
         "confirm": {"type": "boolean"}}, ["material_id", "fields"])),

    # ---- typed UPDATE / soft-delete, one per in-scope object (full CRUD versatility) -------------
    # Each PATCHes (or add/delete) the keyed CHILD row on the object's own OData service. Workflow:
    # discover the exact KEY + field with explore_entity/list_fields/get_*; then change_*(keys, fields).
    # "delete" = SAP soft delete (deletion flag); real archival is out of scope.
    "set_routing_operation": (set_routing_operation, _spec(
        "set_routing_operation", "Repoint a routing OPERATION to a different WORK CENTER — the common "
        "routing edit. USE THIS for 'change the work center of operation 10 to TECHNIC'. Give just "
        "material + operation NUMBER + work-center code/name; it resolves the routing group, the "
        "operation's internal OData key, and the WorkCenterInternalID for you (do NOT hand-build routing "
        "keys — that fails). confirm=false PREVIEWS; confirm=true COMMITS.",
        {"material": {"type": "string", "description": "the made material whose routing to edit"},
         "operation": {"type": "string", "description": "operation NUMBER from get_routing, e.g. '10'"},
         "work_center": {"type": "string", "description": "target work-center code/name, e.g. 'TECHNIC'"},
         "plant": {"type": "string", "description": "default system plant"},
         "confirm": {"type": "boolean"}}, ["material", "operation", "work_center"])),

    "get_routing": (get_routing, _spec(
        "get_routing", "READ the routing (operation sequence + each operation's work center) for a "
        "MATERIAL. Use to show/inspect a routing before editing it with set_routing_operation.",
        {"material": {"type": "string"}, "plant": {"type": "string"}}, ["material"])),

    "change_routing": (change_routing, _spec(
        "change_routing", "ADVANCED generic UPDATE of a ROUTING row (API_PRODUCTION_ROUTING). For the "
        "common case of moving an operation to a different work center, prefer set_routing_operation — it "
        "resolves the key for you. Use change_routing only for other fields, and ONLY with the EXACT "
        "ProductionRoutingOperation key (ProductionRoutingGroup, ProductionRouting, ProductionRoutingSequence, "
        "ProductionRoutingOpIntID, ProductionRoutingOpIntVersion) read from explore_entity — the op NUMBER "
        "is NOT the OpIntID. The work center field is WorkCenterInternalID (an id), not WorkCenter. "
        "confirm=false PREVIEWS; confirm=true COMMITS.",
        {"entity": {"type": "string", "description": "default ProductionRoutingOperation"},
         "keys": {"type": "object", "description": "FULL internal key (from explore_entity)"},
         "fields": {"type": "object", "description": "{ExactODataField: new_value}, e.g. {\"WorkCenterInternalID\":\"10000010\"}"},
         "operation": {"type": "string", "description": "'update' (default), 'add', or 'delete'"},
         "confirm": {"type": "boolean"}}, ["keys"])),

    "set_supplier_terms": (set_supplier_terms, _spec(
        "set_supplier_terms", "Attempt to correct an EXISTING Purchase Info Record's TERMS — net price, "
        "planned delivery (lead) time, min order qty — by MATERIAL (+ optional supplier). Resolves the "
        "PIR's full key for you and VERIFIES after writing. NOTE: on this S/4 system the info-record OData "
        "API accepts the request (HTTP 204) but IGNORES these field updates — they are effectively set at "
        "CREATION only; the tool will tell you if SAP did not apply them. The PIR net price's real lever is "
        "the PB00 cost CONDITION (change_cost_condition), and prices are best set right at create (genesis "
        "now passes the price). Pass only the field(s) to change. confirm=false PREVIEWS; confirm=true COMMITS.",
        {"material": {"type": "string", "description": "the bought material the PIR is for"},
         "supplier": {"type": "string", "description": "optional; needed if the material has several PIRs"},
         "net_price": {"type": "number", "description": "new net price, e.g. 7.12"},
         "lead_time_days": {"type": "integer", "description": "new planned delivery time (days)"},
         "min_order_qty": {"type": "number", "description": "new minimum order quantity"},
         "plant": {"type": "string", "description": "default system plant"},
         "confirm": {"type": "boolean"}}, ["material"])),

    "change_pir": (change_pir, _spec(
        "change_pir", "ADVANCED generic UPDATE of a Purchasing Info Record row (API_INFORECORD_PROCESS_SRV). "
        "For the common case of fixing price/lead-time/min-qty, prefer set_supplier_terms — it resolves the "
        "key for you. Use change_pir only for other fields, with the EXACT A_PurgInfoRecdOrgPlantData key: "
        "PurchasingInfoRecord, PurchasingInfoRecordCategory ('0'), PurchasingOrganization, Plant (all four — "
        "get them from read_pir/explore_entity). Price field = NetPriceAmount; currency = Currency. "
        "operation 'update'|'add'|'delete'. confirm=false PREVIEWS; confirm=true COMMITS.",
        {"entity": {"type": "string", "description": "default A_PurgInfoRecdOrgPlantData"},
         "keys": {"type": "object", "description": "FULL 4-part key (see description)"},
         "fields": {"type": "object", "description": "e.g. {\"NetPriceAmount\":\"7.12\"}"},
         "operation": {"type": "string", "description": "'update' (default), 'add', or 'delete'"},
         "confirm": {"type": "boolean"}}, ["keys"])),

    "read_cost_condition": (read_cost_condition, _spec(
        "read_cost_condition", "READ the purchasing price CONDITION(s) (PPR0) for a material (+ optional "
        "supplier): record number, rate (the actual price MRP/POs use), currency, validity. Use to verify "
        "a price or before correcting it. Multiple records can exist (repeated genesis runs).",
        {"material": {"type": "string"}, "supplier": {"type": "string", "description": "optional"}}, ["material"])),

    "set_condition_price": (set_condition_price, _spec(
        "set_condition_price", "Correct the PRICE on an existing purchasing price CONDITION — the REAL "
        "lever for what MRP/POs pay (the PIR's NetPriceAmount field is not updatable; this is). Give "
        "material + new price (+ optional supplier); it resolves the condition record and PATCHes its "
        "rate, verifying after. If several conditions exist, pass condition_record to target one. "
        "confirm=false PREVIEWS; confirm=true COMMITS.",
        {"material": {"type": "string"}, "price": {"type": "number", "description": "new condition rate, e.g. 7.12"},
         "supplier": {"type": "string", "description": "optional"},
         "condition_record": {"type": "string", "description": "optional exact ConditionRecord to target"},
         "confirm": {"type": "boolean"}}, ["material", "price"])),

    "change_cost_condition": (change_cost_condition, _spec(
        "change_cost_condition", "UPDATE a purchasing price/cost CONDITION record "
        "(API_PURGPRCGCONDITIONRECORD_SRV) — e.g. a newly agreed net price or validity. keys = the FULL "
        "key (from explore_entity); fields = {\"ConditionRateValue\":\"12.50\"}. NOTE some condition "
        "values live IN the key — change those by delete + add. operation 'update'|'add'|'delete'. "
        "confirm=false PREVIEWS; confirm=true COMMITS.",
        {"entity": {"type": "string", "description": "default A_PurgPrcgConditionRecord"},
         "keys": {"type": "object"}, "fields": {"type": "object"},
         "operation": {"type": "string", "description": "'update' (default), 'add', or 'delete'"},
         "confirm": {"type": "boolean"}}, ["keys"])),

    "change_bom": (change_bom, _spec(
        "change_bom", "UPDATE a BOM item (API_BILL_OF_MATERIAL_SRV) — e.g. change a component quantity, "
        "or 'delete' a line. keys = the FULL MaterialBOMItem key (from get_bom/explore_entity); fields = "
        "{\"BillOfMaterialItemQuantity\":\"2\"}. operation 'update'|'add'|'delete'. confirm=false "
        "PREVIEWS; confirm=true COMMITS. (To add/remove a component you may also use "
        "add_bom_component/remove_bom_component.)",
        {"entity": {"type": "string", "description": "default MaterialBOMItem"},
         "keys": {"type": "object"}, "fields": {"type": "object"},
         "operation": {"type": "string", "description": "'update' (default), 'add', or 'delete'"},
         "confirm": {"type": "boolean"}}, ["keys"])),

    "change_material": (change_material, _spec(
        "change_material", "UPDATE a MATERIAL child entity or mark it for deletion (API_PRODUCT_SRV) — the "
        "generic counterpart to update_material for NON-header views (plant, sales, valuation). For a SOFT "
        "delete, 'update' the deletion flag on the right entity (e.g. set the marked-for-deletion field on "
        "A_ProductPlant). keys = the FULL key (from explore_entity); operation 'update'|'add'|'delete'. "
        "For a simple header field change prefer update_material. confirm=false PREVIEWS; confirm=true COMMITS.",
        {"entity": {"type": "string", "description": "default A_Product; e.g. A_ProductPlant for soft-delete"},
         "keys": {"type": "object"}, "fields": {"type": "object"},
         "operation": {"type": "string", "description": "'update' (default), 'add', or 'delete'"},
         "confirm": {"type": "boolean"}}, ["keys"])),

    "extend_to_plant": (extend_to_plant, _spec(
        "extend_to_plant", "LOW-LEVEL: extend ONE single material's plant + valuation views to a new plant "
        "— one material only, NO BOM / routing / production version / components. To extend a whole ASSEMBLY "
        "(a finished good plus its components, BOM, routing and production version) to a plant — which is "
        "almost always what 'extend <product> to plant <X>' means — use enable_plant_production instead. "
        "Handles the plant relations: flat plant view, MRP type ND by default, valuation currency by plant "
        "(1010=EUR, 1710=USD), valuation class by material type. confirm=false PREVIEWS; confirm=true COMMITS.",
        {"material": {"type": "string", "description": "the existing material number"},
         "plant": {"type": "string", "description": "the target plant, e.g. 1010"},
         "product_type": {"type": "string", "description": "ROH|HAWA|HALB|FERT (drives valuation class)"},
         "mrp_type": {"type": "string", "description": "default ND (no planning)"},
         "standard_price": {"type": "number"}, "currency": {"type": "string", "description": "override; default by plant"},
         "confirm": {"type": "boolean"}}, ["material", "plant"])),

    "list_allowed_values": (list_allowed_values, _spec(
        "list_allowed_values", "List the valid coded values for a field (the live codebook).",
        {"field": {"type": "string"}}, ["field"])),

    "get_valid_storage_locations": (get_valid_storage_locations, _spec(
        "get_valid_storage_locations", "List the VALID storage locations for a plant (SAP config T001L). "
        "Storage locations are plant-specific and are NOT in the codebook — ground one from this list, "
        "never guess or default it.",
        {"plant": {"type": "string", "description": "plant code, e.g. 1010"}}, ["plant"])),

    "get_valid_mrp_controllers": (get_valid_mrp_controllers, _spec(
        "get_valid_mrp_controllers", "List the VALID MRP controllers for a plant (SAP config T024D). A "
        "planning MRP type (e.g. PD) REQUIRES an MRP controller; ground it from this list — never guess or omit it.",
        {"plant": {"type": "string", "description": "plant code, e.g. 1010"}}, ["plant"])),

    "find_work_center": (find_work_center, _spec(
        "find_work_center", "LIST or resolve the work centers at a plant. Work centers are master-data "
        "objects (CR03), NOT a codebook field — so to LIST every work center for a plant, call this with a "
        "blank or generic query (e.g. query='') and it returns all of them (code + internal id + "
        "description). To RESOLVE one, pass a code/name/alias ('PACK01', 'packaging', 'assembly') and it "
        "returns the SAP internal id needed by create_routing. Backed by a map verified from live routing "
        "operations (mcp_server/work_centers.json).",
        {"query": {"type": "string", "description": "work-center code/name/alias to resolve; blank '' = list ALL for the plant"},
         "plant": {"type": "string", "description": "plant code, default 1710"}}, ["query"])),

    "refresh_relationship": (refresh_relationship, _spec(
        "refresh_relationship", "Re-read a plant-keyed config relationship from SAP (clears the cache); "
        "use after a governed config change. relationship: 'storage_location' | 'mrp_controller'.",
        {"relationship": {"type": "string"}, "plant": {"type": "string"}}, ["relationship", "plant"])),

    "find_field": (find_field, _spec(
        "find_field", "Resolve a user's term to the exact OData field name from live $metadata.",
        {"term": {"type": "string"}}, ["term"])),

    "run_genesis": (run_genesis, _spec(
        "run_genesis", "Design2Make: create a whole assembly's master data from a spec (parent FERT -> "
        "components -> PIR/cost for bought -> BOM -> routing -> production version). confirm=false "
        "PREVIEWS the plan (no writes); confirm=true COMMITS. Build the spec from the image; do NOT "
        "call the individual create tools -- run_genesis owns the whole write chain.",
        {"spec": {"type": "object", "description": "{parent:{description,type}, components:[{name,description,"
                  "type(HAWA/HALB/FERT),role(bought/made),vendor,price,quantity}], routing?:[{operation,text,work_center}], "
                  "dedup?:bool (OPTIONAL — leave it OUT. The rig controls reuse via GENESIS_DEDUP, "
                  "currently OFF = always create fresh, never reuse old materials. Do not set this true.)}"},
         "confirm": {"type": "boolean"}}, ["spec"])),

    "load_bom_from_file": (load_bom_from_file, _spec(
        "load_bom_from_file", "Design2Make from a FILE: deterministically parse a tabbed-Excel BOM "
        "(sheets 'BOM' + 'Operations') into a genesis spec and build the WHOLE assembly -- multi-level, "
        "with PIR + cost for EVERY bought part at EVERY level. Use for 'load/build/upload the BOM from "
        "<file>.xlsx' or scale-test files (50/100/150/200 parts). NO vision model -- lossless & "
        "reproducible. confirm=false PREVIEWS the plan (no writes); confirm=true COMMITS. Prefer this "
        "over run_genesis whenever the user names an .xlsx BOM file. Set enrich=true ONLY if the user asks "
        "to web-source / look up prices for parts left blank (opt-in; costs web calls); default off keeps "
        "the run fully deterministic.",
        {"path": {"type": "string", "description": "path to the .xlsx BOM file, e.g. bom_50.xlsx"},
         "confirm": {"type": "boolean"},
         "enrich": {"type": "boolean", "description": "opt-in: web-source a real price for bought parts "
                    "whose price is blank, before preview/commit. Default false."}}, ["path"])),
    "reconcile_routings": (reconcile_routings, _spec(
        "reconcile_routings", "PRE-vs-POST routing reconciliation: for a committed file-genesis, compare the "
        "work centers each made node's routing was PLANNED with (from the BOM file) vs what was actually "
        "CREATED in SAP -- MATCH / DRIFT / MISSING per node. Use when the user asks to 'recon routings', "
        "'compare planned vs actual routings', or check if routings match the plan. Read-only.",
        {"bom_file": {"type": "string", "description": "the committed .xlsx BOM, e.g. bom_auto_300.xlsx"},
         "fert": {"type": "string", "description": "the FERT material number created by that genesis, e.g. 13973"},
         "plant": {"type": "string", "description": "plant (default 1710)"}}, ["bom_file", "fert"])),

    "enable_plant_production": (enable_plant_production, _spec(
        "enable_plant_production", "THE tool for 'extend <product/assembly> to plant <X>' / 'make <product> "
        "available / plannable / producible in plant <X>'. Extends an EXISTING assembly to ANOTHER plant in "
        "ONE grounded call: extend the FG + EVERY BOM component to the plant, add the work-scheduling view, "
        "set a planning MRP type + a controller resolved for THIS plant, build the plant BOM, create a "
        "routing on a grounded plant work center, bind production version 0001, and optionally create demand "
        "+ run MRP. ALWAYS prefer this over the one-by-one extend_to_plant / create_bom / create_routing "
        "tools for any whole-assembly plant extension. confirm=false returns the grounded PLAN (no writes); "
        "confirm=true executes.",
        {"material": {"type": "string", "description": "the FERT assembly (already created at its birth plant)"},
         "plant": {"type": "string", "description": "the TARGET plant to enable, e.g. 1010"},
         "components": {"type": "array", "items": {"type": "object"},
                        "description": "[{component, quantity}] or [matnr]; omit to read the source-plant BOM"},
         "mrp_controller": {"type": "string", "description": "DISPO for the plant; default = first valid"},
         "work_center": {"type": "string", "description": "routing work center; default = first valid for the plant"},
         "mrp_type": {"type": "string", "description": "planning MRP type (default PD; ND = no planning)"},
         "source_plant": {"type": "string", "description": "plant to read the existing BOM from (default birth plant)"},
         "demand_qty": {"type": "number", "description": "if > 0, create demand for this qty and run MRP after"},
         "confirm": {"type": "boolean"}}, ["material", "plant"])),

    "get_bom": (get_bom, _spec(
        "get_bom", "READ an existing Bill of Material — the parent's components and quantities.",
        {"material": {"type": "string", "description": "the parent/assembly material"},
         "plant": {"type": "string"}, "alternative": {"type": "string"}}, ["material"])),

    "add_bom_component": (add_bom_component, _spec(
        "add_bom_component", "Add ONE component to an EXISTING BOM alternative (finds the BOM, picks the "
        "next free item number, POSTs the item). Use this to add a part to a parent's BOM. "
        "confirm=false PREVIEWS; confirm=true COMMITS.",
        {"material": {"type": "string", "description": "the parent material whose BOM to edit"},
         "plant": {"type": "string"}, "component": {"type": "string", "description": "the component material to add"},
         "alternative": {"type": "string"}, "quantity": {"type": "number"}, "unit": {"type": "string"},
         "confirm": {"type": "boolean"}}, ["material", "plant", "component"])),

    "remove_bom_component": (remove_bom_component, _spec(
        "remove_bom_component", "Remove a component from an EXISTING BOM alternative by component number. "
        "confirm=false PREVIEWS; confirm=true COMMITS.",
        {"material": {"type": "string"}, "plant": {"type": "string"}, "component": {"type": "string"},
         "alternative": {"type": "string"}, "confirm": {"type": "boolean"}}, ["material", "plant", "component"])),

    "create_bom": (create_bom, _spec(
        "create_bom", "Create a NEW Bill of Material (parent + its components). Use add_bom_component to "
        "extend an existing BOM instead. confirm=false PREVIEWS; confirm=true COMMITS.",
        {"material": {"type": "string"}, "plant": {"type": "string"},
         "components": {"type": "array", "items": {"type": "object"},
                        "description": "[{component, quantity, unit?, item_category?}]"},
         "confirm": {"type": "boolean"}}, ["material", "plant", "components"])),

    "read_production_version": (read_production_version, _spec(
        "read_production_version", "READ the production version(s) for a MADE material (FERT/HALB) at a "
        "plant, from table MKAL. Returns each version + the BOM it binds (alt/usage). Empty (count 0) = "
        "NO production version exists yet — a gap; every made material needs one.",
        {"material": {"type": "string", "description": "the made material (FERT or HALB)"},
         "plant": {"type": "string", "description": "plant, e.g. 1710"}}, ["material"])),

    "read_routing": (read_routing, _spec(
        "read_routing", "READ the routing(s) assigned to a MADE material (FERT/HALB) at a plant, from "
        "table MAPL. Returns each routing group/counter. Empty (count 0) = NO routing exists yet — a "
        "gap; every made material needs its own routing.",
        {"material": {"type": "string", "description": "the made material (FERT or HALB)"},
         "plant": {"type": "string", "description": "plant, e.g. 1710"}}, ["material"])),

    "read_pir": (read_pir, _spec(
        "read_pir", "READ the Purchase Info Record(s) for a MATERIAL (a bought-out / HAWA component): "
        "each supplier's net price, currency, lead time and min order qty. Use to CONFIRM a bought "
        "component actually HAS a PIR with a committed price. If it returns no record, the material has "
        "NO PIR yet (a gap). A material number is NOT a PIR number.",
        {"material": {"type": "string", "description": "the bought component's material number"},
         "supplier": {"type": "string", "description": "optional supplier/vendor filter"}}, ["material"])),

    "create_info_record": (create_info_record, _spec(
        "create_info_record", "Create a Purchase Info Record (PIR) for a BOUGHT component: links the "
        "material to its supplier with a net price + lead time, so MRP can raise a purchase requisition. "
        "Every HAWA/bought-out component needs one. confirm=false PREVIEWS; confirm=true COMMITS.",
        {"material": {"type": "string"}, "supplier": {"type": "string", "description": "supplier/vendor code, e.g. 17300001"},
         "net_price": {"type": "number", "description": "the component's net price"},
         "currency": {"type": "string"}, "lead_time_days": {"type": "integer"},
         "purchasing_org": {"type": "string", "description": "default 1710"},
         "confirm": {"type": "boolean"}}, ["material", "supplier"])),

    "create_cost_condition": (create_cost_condition, _spec(
        "create_cost_condition", "Commit the purchasing PRICE condition (PPR0) for a bought "
        "material/supplier — the actual cost price in SAP (optionally with qty price-breaks). Call after "
        "create_info_record to write the (e.g. web-sourced) price, not leave it as a preview. "
        "confirm=false PREVIEWS; confirm=true COMMITS.",
        {"material": {"type": "string"}, "supplier": {"type": "string"},
         "price": {"type": "number", "description": "the committed net price"},
         "currency": {"type": "string"}, "purchasing_org": {"type": "string"},
         "confirm": {"type": "boolean"}}, ["material", "supplier", "price"])),

    "create_demand": (create_demand, _spec(
        "create_demand", "Create Planned Independent Requirements (forecast) DEMAND for a make-to-stock "
        "finished good — type VSF/version 00 via API_PLND_INDEP_RQMT_SRV (the make-to-stock signal MRP "
        "consumes, NOT a sales order). Runs on the remote mcp-demand server (:8003). For ONE month set "
        "period (YYYYMM; default next month). For demand 'each month' across a SPAN, make a SINGLE call "
        "with period=START YYYYMM and period_to=END YYYYMM (e.g. period=202607, period_to=202612 = "
        "quantity each month Jul–Dec 2026) — do NOT call this tool once per month. confirm=false "
        "PREVIEWS; confirm=true COMMITS. If it returns an ERROR about reaching the server, the demand "
        "did NOT run — say so; never claim success.",
        {"material": {"type": "string", "description": "the finished-good material number"},
         "plant": {"type": "string"}, "quantity": {"type": "string", "description": "units per month"},
         "period": {"type": "string", "description": "YYYYMM; default next month. START of the range if period_to is set"},
         "period_to": {"type": "string", "description": "END YYYYMM; set with period to write one bucket per month across the span in ONE call"},
         "confirm": {"type": "boolean"}}, ["material"])),

    "read_demand": (read_demand, _spec(
        "read_demand", "READ existing Planned Independent Requirements (header + per-period quantities) "
        "for a material+plant from API_PLND_INDEP_RQMT_SRV (mcp-demand :8003). Use to VERIFY that demand "
        "actually persisted. An empty result means NO PIR demand exists yet for that material.",
        {"material": {"type": "string"}, "plant": {"type": "string"}}, ["material"])),

    "run_mrp": (run_mrp, _spec(
        "run_mrp", "Run MRP for a material and return the planned cascade (planned orders + purchase reqs "
        "per BOM level). multi_level=true plans the whole BOM (MD02); false = header only (MD03). Runs on "
        "the remote NWRFC planning server. confirm=false PREVIEWS; confirm=true COMMITS. An ERROR about "
        "reaching the server means MRP did NOT run — say so; never claim success.",
        {"material": {"type": "string"}, "plant": {"type": "string"},
         "multi_level": {"type": "boolean"},
         "planning_mode": {"type": "string", "description": "'1'=adapt (normal), '3'=delete & recreate (demo)"},
         "confirm": {"type": "boolean"}}, ["material"])),

    "read_mrp_list": (read_mrp_list, _spec(
        "read_mrp_list", "READ the MD04 stock/requirements list for a material — every supply & demand "
        "element the MRP run PRODUCED: plant stock, planned orders, purchase requisitions, planned "
        "independent requirements, sales orders, dependent requirements — each with date, quantity and "
        "running available quantity. This is how you VERIFY an MRP execution (e.g. demand is covered by a "
        "planned order, components exploded into dependent reqs). Read-only (mcp-mrp :8004). 'No MRP "
        "elements' means MRP has not produced anything yet for that material.",
        {"material": {"type": "string"}, "plant": {"type": "string"},
         "area": {"type": "string", "description": "MRP area; defaults to plant"}}, ["material"])),

    "read_mrp_material": (read_mrp_material, _spec(
        "read_mrp_material", "READ the MRP material master for a material @ plant: procurement type "
        "(E in-house / F external), low-level code, base unit, material type/group, MRP area. Read-only "
        "(mcp-mrp :8004).",
        {"material": {"type": "string"}, "plant": {"type": "string"},
         "area": {"type": "string", "description": "MRP area; defaults to plant"}}, ["material"])),

    "google_search": (google_search, _spec(
        "google_search", "Web search for prices, specs, weights, dimensions (e.g. 'ASUS ROG 16GB DDR5 price').",
        {"query": {"type": "string"}}, ["query"])),

    "load_skill": (_load_skill, _spec(
        "load_skill", "Load a skill's full instructions (its SKILL.md body) ONLY when that skill applies "
        "(see the AVAILABLE SKILLS index in the system prompt). The body is not in context until you call this.",
        {"name": {"type": "string"}}, ["name"])),

    "run_skill_script": (_run_skill_script, _spec(
        "run_skill_script", "Execute a skill's script and return ONLY its output (run, don't read -- the "
        "script source never enters context).",
        {"name": {"type": "string"}, "script": {"type": "string"},
         "args": {"type": "array", "items": {"type": "string"}}}, ["name", "script"])),

    "write_skill_artifact": (_write_skill_artifact, _spec(
        "write_skill_artifact", "Persist a skill artifact YOU composed as REAL files into the current "
        "session's assets/<skill_name>/ (e.g. SCHEMA.md, MAPPING.md, TEMPLATE.md). Nothing durable yet -- "
        "the user reviews, then you promote_skill with their approval. Use this when the user demonstrates "
        "something (a screen, a report) and asks you to turn it into a reusable skill.",
        {"skill_name": {"type": "string", "description": "kebab-case folder name, e.g. md04-card-skill"},
         "files": {"type": "object", "description": "{filename: text-content}, one entry per artifact file"}},
        ["skill_name", "files"])),

    "promote_skill": (_promote_skill, _spec(
        "promote_skill", "HUMAN-GATED: with the user's EXPLICIT approval, copy a reviewed artifact from the "
        "session's assets/ into the durable skills/<name>/ + write SKILL.md, so it is indexed, "
        "load_skill-able, and triggers thereafter. confirm=false PREVIEWS; set confirm=true ONLY after the "
        "user approves.",
        {"skill_name": {"type": "string"},
         "description": {"type": "string", "description": "one-line description for the skills index"},
         "when_to_trigger": {"type": "string", "description": "phrases/events that invoke it, e.g. 'show MD04', 'MD04 card', after run_mrp"},
         "confirm": {"type": "boolean"}}, ["skill_name"])),

    "render_card": (_render_card, _spec(
        "render_card", "Render a card YOU composed into the STRUCTURED-DATA panel (not just chat). content "
        "is the card body as HTML or Markdown (e.g. a skill TEMPLATE populated with live data). Use this as "
        "the FINAL step of a card-rendering skill so the result surfaces as a typed card, not buried in chat.",
        {"title": {"type": "string"}, "subtitle": {"type": "string"},
         "content": {"type": "string", "description": "the card body, HTML or Markdown"}}, ["title", "content"])),
}

# Optionally re-point SAP tools at the CLOUD MCP fleet instead of in-process OData (flag SAP_VIA_MCP).
# No-op unless the flag is on, so the in-process path stays the default. Lets us migrate object-by-object
# and retire the local :8001-:8004 once everything routes through the cloud mcp-* servers.
try:
    import mcp_route as _mcp_route                       # noqa: E402
    TOOLS = _mcp_route.apply(TOOLS)
except Exception as _e:                                  # never let routing wiring break the registry
    pass

TOOL_SPECS = [spec for _, spec in TOOLS.values()]


def dispatch(name: str, args: dict) -> str:
    """Call a registered tool by name. Returns its string result (errors are returned, not raised,
    so the loop can show the model what went wrong and recover)."""
    entry = TOOLS.get(name)
    if entry is None:
        return f"ERROR: unknown tool '{name}'"
    fn, _ = entry
    try:
        out = fn(**(args or {}))
        return out if isinstance(out, str) else str(out)
    except Exception as e:
        return f"ERROR calling {name}: {type(e).__name__}: {e}"
