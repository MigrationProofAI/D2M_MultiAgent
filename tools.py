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
                 build_material_payload, list_allowed_values, find_field, extend_to_plant)
from genesis import run_genesis, enable_plant_production   # noqa: E402  -- Design2Make orchestration + one-call plant enablement
from make import (get_bom, add_bom_component, remove_bom_component, create_bom)  # noqa: E402  -- post-genesis BOM edits
from planning_client import create_demand, run_mrp   # noqa: E402  -- SSE bridge to the NWRFC planning server (:8001)
from serper import google_search           # noqa: E402  -- web search for prices / specs
from config_graph import (get_valid_storage_locations, get_valid_mrp_controllers,   # noqa: E402
                          refresh_relationship)        # plant-keyed config (T001L / T024D), not in the codebook


def _spec(name, desc, props, required):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props, "required": required}}}


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
        "get_material", "Read a material/product master by ID from SAP S/4HANA.",
        {"material_id": {"type": "string", "description": "exact material number"},
         "full": {"type": "boolean", "description": "true = all header fields"}}, ["material_id"])),

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
                  "dedup?:bool (default true; false = force a FRESH build, no reuse)}"},
         "confirm": {"type": "boolean"}}, ["spec"])),

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

    "create_demand": (create_demand, _spec(
        "create_demand", "Create sales-order DEMAND for a finished good (each call adds a new order, so "
        "demand accumulates). Runs on the remote NWRFC planning server. confirm=false PREVIEWS; "
        "confirm=true COMMITS. If it returns an ERROR about reaching the server, the demand did NOT run — "
        "say so; never claim success.",
        {"material": {"type": "string", "description": "the finished-good material number"},
         "plant": {"type": "string"}, "quantity": {"type": "string"},
         "customer": {"type": "string", "description": "sold-to, default USCU_S03"},
         "confirm": {"type": "boolean"}}, ["material"])),

    "run_mrp": (run_mrp, _spec(
        "run_mrp", "Run MRP for a material and return the planned cascade (planned orders + purchase reqs "
        "per BOM level). multi_level=true plans the whole BOM (MD02); false = header only (MD03). Runs on "
        "the remote NWRFC planning server. confirm=false PREVIEWS; confirm=true COMMITS. An ERROR about "
        "reaching the server means MRP did NOT run — say so; never claim success.",
        {"material": {"type": "string"}, "plant": {"type": "string"},
         "multi_level": {"type": "boolean"},
         "planning_mode": {"type": "string", "description": "'1'=adapt (normal), '3'=delete & recreate (demo)"},
         "confirm": {"type": "boolean"}}, ["material"])),

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
