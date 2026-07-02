# MCP migration — route all SAP calls through the cloud `mcp-*` fleet

**Goal:** the rig stops being an OData/RFC client and becomes a pure **MCP client** to the CF `d2m-cf`
fleet, so the in-process wrappers (`sap.py`/`make.py`) and the local `:8001`–`:8004` servers can be
retired. **Done-criteria (the proof):** the rig no longer needs `SAP_HOST`/`SAP_USER`/`SAP_PASS` — only
`*_MCP_URL`s. A `grep` for `sap_session` / `requests.*BASE` in the rig returns zero on the live path.

## The switch
Everything is gated by **`SAP_VIA_MCP`** (default **off** → in-process path, demo-safe).
`SAP_VIA_MCP=on` →
- the agent's SAP tools re-point to the cloud (`tools.py` → `mcp_route.apply`),
- **genesis's internal chain** re-points too (`genesis.py` rebinds its `sap.py`/`make.py` names to
  `mcp_route.s_*` shims),
- `planning_client.py` / `genesis.py` point demand/MD04/MRP-run/prod-version at the **CF routes**
  (retiring local `:8001`–`:8004`).

URLs live in `mcp_server/mcp_route.py` → `SERVERS` (env-overridable; `CF_DOMAIN` sets the base, default
`cfapps.us10.hana.ondemand.com`). Per-server env: `MATERIAL_MCP_URL`, `BOM_MCP_URL`, `ROUTING_MCP_URL`,
`PIR_MCP_URL`, `COSTCOND_MCP_URL`, `DEMAND_MCP_URL`, `MRPVIEW_MCP_URL`, `PLANNING_MCP_URL`, `PRODVER_MCP_URL`.

## Routed to cloud (verified live, read + preview)
| Object | Cloud server | Rig tools routed | Cloud tool |
|---|---|---|---|
| Material | `mcp-material` | get_material→**read_material**; create_material→**change_material add**; update_material/change_material→change_material; extend_to_plant | |
| BOM | `mcp-bom` | get_bom, create_bom, change_bom | |
| Routing | `mcp-routing` | get_routing, create_routing, change_routing, find_work_center | |
| PIR | `mcp-pir` | read_pir, create_info_record, change_pir | |
| Cost | `mcp-costcond` | read/create/change_cost_condition | |
| Demand | `mcp-plndindepreqmt` | create_demand→**create_plndindepreqmt**, read_demand→read_plndindepreqmt (via planning_client) | |
| MD04 | `mcp-mrp` | read_mrp_list, read_mrp_material (via planning_client) | |
| MRP run | `sap-planning-mcp` (SSE) | run_mrp | |
| Prod version | `sap-prodvers-mcp` (SSE) | read/create production version (genesis) | |
| Grounding | `mcp-config-graph` (SSE) | list_allowed_values, get_valid_storage_locations, get_valid_mrp_controllers, refresh_relationship | (staged — set `CONFIG_GRAPH_MCP_URL` once deployed) |

**`create_material` note:** the cloud `create_material` rebuilds the payload from high-level args, which
would drop the rig's grounded `build_material_payload` deep-insert. So it routes through the cloud's
generic **`change_material` with `operation="add"`** — POSTs the rig's `fields` straight to `A_Product`
(identical to in-process; new Product echoes back for the verifier anchor).

## Still in-process (by design) — NOT yet on the cloud
| Tool(s) | Why |
|---|---|
| `search_materials` | no cloud search tool on `mcp-material`. |
| `build_material_payload` | local helper, no SAP call. |
| `find_field` | OData `$metadata` resolver — **no cloud tool** on `mcp-config-graph`. Stays in-process (lone residual SAP dependency on the agent tool surface). |
| `add_bom_component`, `remove_bom_component` | resolvers — re-implement as cloud `get_bom`(parse next item / item key) + `change_bom` add/delete. |
| `set_condition_price` | resolver — cloud `read_cost_condition`(parse ConditionRecord+currency) + `change_cost_condition` (send rate **and** currency). |
| `set_supplier_terms` | resolver — and PIR field-update is **SAP-ignored** anyway; price belongs on the condition. |
| `set_routing_operation` | **cloud gap:** `mcp-routing.get_routing` returns only the material *assignment* (group/counter), **no operations** — can't resolve the operation key over the cloud. **Add an operation-read tool to `mcp-routing`**, or keep this in-process. |

These are ergonomics, not blockers — the agent can use the routed `read_*` + `change_*` directly.

## Validated so far (CAL license restored)
- `get_material(12174)` via `mcp-material` → real FERT from SAP ✅ (transport + open CF route + SAP round-trip).
- `create_material` route → cloud preview `POST /API_PRODUCT_SRV/A_Product` (grounded deep-insert) ✅.
- Genesis shims preview: `create_bom`→`POST MaterialBOM`, `create_cost_condition`→`POST A_PurgPrcgConditionRecord`,
  `change_material_view`→`PATCH A_ProductPlant` (service→server mapping) ✅; genesis rebinds confirmed ✅.

## Still to verify (write-level, per object) — flip `SAP_VIA_MCP=on`, then:
1. For each object: **create (confirm=true) → read back → verify** through the cloud == the in-process result.
2. **Run a full genesis** (confirm=true) end-to-end on the cloud path; confirm the verify→heal loop still
   certifies (watch the two parity items below).
3. **Parity items:**
   - **(#2 — RESOLVED)** created-material anchor: the cloud create echo truncates and exposes the new
     number only in the `__metadata` id, so `"Product":"(\w+)"` returned None → genesis would abort.
     Fixed rig-side in `mcp_route._norm_create` (prepends `"Product":"<matnr>"`); verified live —
     `genesis._new_matnr` extracts `12257` from a cloud create. No d2m-cf change needed.
   - **(#1 — STILL OPEN)** cloud tools return **plain text, no `@@DATA@@` cards** → the Structured-Data
     panel stays blank on the cloud path until the routed returns are wrapped into cards.

**Live write receipts:** materials `12256`, `12257` (HAWA, "ZZ MCP Route Test") created via cloud + read
back — throwaway test artifacts, safe to mark for deletion.

## Full cloud genesis test (session 43081edd) — WRITES all pass
End-to-end with `SAP_VIA_MCP=on`, locals down: material · BOM · PIR · cost · **routing · production
version · demand · MRP run** all **created successfully** through the CF fleet. Only the verifier's
*read-backs* of routing + PV failed — root cause below.

### CF RFC servers expose FEWER tools than the local ones (deploy gap)
- `sap-prodvers-mcp` (CF) → **only `create_production_version`** (local `:8002` also had
  `read_production_version` + `read_routing`).
- `sap-planning-mcp` (CF) → `create_demand`, `run_mrp`.

Effect: the verifier's `read_production_version` / `read_routing` returned "Unknown tool" → routing + PV
shown UNVERIFIED (even though both were created).

**Mitigations (rig-side, done):** `read_routing` now verifies via OData `mcp-routing.get_routing`
(assignment = group/counter → exists); `read_production_version` returns an honest "read unavailable on
cloud, do NOT treat as missing" message (MKAL is RFC-only, no OData path).

**Proper fix (server-side, for the d2m-cf CC):** add **`read_production_version`** (and ideally
`read_routing`) back to **`sap-prodvers-mcp`** so the PV can be read-verified on the cloud.

## Retire / done
- Stop running local `:8001`–`:8004` (the flag points everything at CF).
- Address `search_materials` + the routing operation-read gap + re-implement the resolvers over cloud read+change.
- Grounding routing is **staged** (`mcp-config-graph`); once it's pushed, set `CONFIG_GRAPH_MCP_URL` and test.
- **Codebook single-source (S5 — server-side):** the rig still reads a local static `code_book.json` for
  `grounding.enforce` (a validation gate) + `build_material_payload`. This is reference data, NOT a creds
  dependency (doesn't block dropping creds) — but it can DRIFT from `mcp-config-graph`. Proper fix: have
  `mcp-config-graph` expose codes **machine-readable** (structured `list_allowed_values` or a
  `get_allowed_codes(field)`), then grounding fetches structured codes (cache per field) and the rig
  carries no codebook. Avoid parsing the formatted text for a blocking decision.
- **Genesis-internal grounding — DONE** ✅ `config_graph._read_relation` reroutes to `mcp-config-graph`
  under the flag (get_relation / validate_plant_config / is_valid all cloud-grounded; verified live).
- **Post-CC update (CF tools added):** `mcp-routing.read_production_version` (PV verify ✅ S1),
  `mcp-material.search_material` (✅ S3), `mcp-bom.add_/remove_component` (BOM resolvers ✅) — all now
  routed + live-verified. `mcp-mrp.read_mrp_tree` + `mcp-material.write_product_text` also added (not yet
  wired in the rig).
- **`set_condition_price` — DONE** ✅ now orchestrates cloud `read_cost_condition` + `change_cost_condition`
  (regex-salvages the cloud read, which truncates at 2500 chars). Live-verified: 12220 rate 7.12→8.25, 204.
- **Remaining in-process residuals (3):** `set_supplier_terms` (moot — SAP ignores PIR field update),
  `set_routing_operation` (blocked — **S2**: `mcp-routing` has no operation read), `find_field` (**S4**).
  Plus codebook single-source (**S5**) and `grounding.enforce`'s local code-set read.
- **S6 (server-side):** cloud read tools **truncate text at ~2500 chars**, breaking JSON parsing for
  multi-row reads (`read_cost_condition`, the create echo). Rig works around it with regex; the clean fix
  is for the cloud tools to return full/structured payloads (also helps any future programmatic consumer).
- **Remove `SAP_HOST`/`SAP_USER`/`SAP_PASS`** from the rig — only after the residuals above are cloud-routed;
  that removal is the completion proof.

## Files
`mcp_server/mcp_route.py` (registry + routes + genesis shims + flag), `tools.py` (applies routing),
`mcp_server/planning_client.py` + `mcp_server/genesis.py` (CF re-point + genesis rebind under the flag).
