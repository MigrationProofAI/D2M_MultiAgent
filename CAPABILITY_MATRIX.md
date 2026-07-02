# Design2Make — Capability Matrix (Agents · Skills · MCP · Tools · Model)

Verified against the rig + the CF `mcp-*` fleet (cloud mode, `SAP_VIA_MCP=on`).

## 1. Agents → authority · skills · model
| Agent | Role | Authority (tools) | Skills it leans on | Model |
|---|---|---|---|---|
| **Maker** | Builds the master data | **all write tools** (create/change material·BOM·routing·PIR·cost, extend, demand, MRP) — *no* `search_materials` | material-create · bom-precondition · codebook-grounding · mrp-type-pd-checklist · org-extension | Claude on SAP AI Core |
| **Verifier** | Independently re-reads SAP & certifies | **read-only set** (get/read_* · find_work_center) — *no search, no write* | genesis-verifier · plant-view-verifier · independent-certification-report | Claude on SAP AI Core |
| **Conductor** | Orchestrates the agents (sequential · parallel · loop · hybrid) | orchestration only (no SAP tools) | — | Claude on SAP AI Core |
| **Board — Engineering** | Reviews BOM/routing/make-vs-buy | pure reasoning (no tools) | codebook-consult | Claude on SAP AI Core |
| **Board — Procurement** | Reviews supplier/PIR/price/lead-time | pure reasoning | codebook-consult | Claude on SAP AI Core |
| **Board — Compliance** | Reviews coded values / governance | pure reasoning | codebook-consult | Claude on SAP AI Core |
| **Board — Finance** | Reviews valuation/price control | pure reasoning | codebook-consult | Claude on SAP AI Core |
| **Board — Planning** | Reviews MRP type/controller/PV | pure reasoning | codebook-consult | Claude on SAP AI Core |
| **Chair** | Synthesises the board into one go/no-go | reasoning only | — | Claude on SAP AI Core |
| **Guide** | Explains the platform (voiced) | none (explain-only) | — | Claude on SAP AI Core (+ nova voice) |

Authority is enforced at dispatch via `allowed_tools` — not by trust.

## 2. MCP servers (CF fleet) → transport · SAP backing · tools
| MCP server | Transport | SAP service / RFC | Tools |
|---|---|---|---|
| `mcp-material` | streamable-http | API_PRODUCT_SRV | create/read/change_material · extend_to_plant · search_material · write_product_text |
| `mcp-bom` | streamable-http | API_BILL_OF_MATERIAL_SRV;v=2 | create_bom · get_bom · list_components · change_bom · add/remove_component |
| `mcp-routing` | streamable-http | API_PRODUCTION_ROUTING | find_work_center · create_routing · get_routing · change_routing · read_production_version |
| `mcp-pir` | streamable-http | API_INFORECORD_PROCESS_SRV | create_info_record · read_pir · change_pir |
| `mcp-costcond` | streamable-http | API_PURGPRCGCONDITIONRECORD_SRV | create/read/change_cost_condition |
| `mcp-plndindepreqmt` | streamable-http | API_PLND_INDEP_RQMT_SRV | create/read/change_plndindepreqmt (VSF/00 demand) |
| `mcp-mrp` | streamable-http | API_MRP_MATERIALS_SRV_01 | read_mrp_list · read_mrp_tree · read_mrp_material · read_mrp_elements_raw |
| `sap-planning-mcp` | SSE (NWRFC) | **BAPI_MATERIAL_PLANNING** | run_mrp (+ create_demand legacy) |
| `sap-prodvers-mcp` | SSE (NWRFC) | **ZD2M_PROD_VERS_MAINTAIN** (table MKAL) | create_production_version |
| `mcp-config-graph` | SSE | codebook + plant config (OData/T001L/T024D) | list_allowed_values · get_valid_storage_locations · get_valid_mrp_controllers · refresh_relationship · validate_plant_config |
| `agent-ui` | HTTP + WebSocket | the rig itself (orchestration + UI) | — |

## 3. Rig tools → MCP server (cloud mode)
| Rig tool | → cloud server.tool |
|---|---|
| get_material · create_material · update_material · change_material · extend_to_plant · search_materials | mcp-material (`read_material`/`change_material add`/`change_material`/`search_material`) |
| get_bom · create_bom · change_bom · add_bom_component · remove_bom_component | mcp-bom (`add_component`/`remove_component`) |
| get_routing · create_routing · change_routing · find_work_center · read_routing · read_production_version | mcp-routing |
| read_pir · create_info_record · change_pir | mcp-pir |
| read_cost_condition · create_cost_condition · change_cost_condition · **set_condition_price** | mcp-costcond (set_condition_price orchestrates read+change) |
| create_demand · read_demand | mcp-plndindepreqmt |
| read_mrp_list · read_mrp_material | mcp-mrp |
| run_mrp | sap-planning-mcp (RFC) |
| read/create production version (in genesis) | sap-prodvers-mcp create + mcp-routing read |
| list_allowed_values · get_valid_storage_locations · get_valid_mrp_controllers · refresh_relationship | mcp-config-graph |
| run_genesis · enable_plant_production | orchestrate the above (cloud shims) |
| **still in-process:** find_field · set_supplier_terms (moot) · set_routing_operation (needs S2) | — (local OData) |
| **local, no SAP:** build_material_payload · google_search · load/run_skill · write/promote_skill · render_card | — |

## 4. Skills
| Skill | Purpose |
|---|---|
| material-create | create a material master (FERT/HALB/HAWA/ROH) with verified codes + confirm-gate |
| bom-precondition | preconditions/checklist for BOM/genesis writes (plant ext, routing, PV, PIR, price, country) |
| codebook-consult | query the live codebook for valid values before coding a component |
| codebook-grounding | ground every coded field from the codebook/plant config before writing |
| genesis-verifier | read-only certifier — re-read SAP & certify every object the SPEC requires |
| plant-view-verifier | verify every assembly material has a valid plant view at a target plant |
| independent-certification-report | end-of-session certification card (objects, demand, MRP cascade) |
| mrp-type-pd-checklist | verify all BOM materials have MRPType=PD + controller after a write |
| mrp-plant-extension-lessons | API lessons for plant extension / MRP fields |
| org-extension | extend an existing material to a new plant without creating/altering basics |
| d2m-render / md04-card-skill / mm03-card-skill / mm03-mrp-skill | render results (material, MD04, MM03 views) as structured cards |

## 5. Model layer
| Role | Model | Host |
|---|---|---|
| Reasoning / orchestration (all agents) | **Claude (Sonnet) ** | SAP AI Core (`MODEL_PROVIDER=anthropic`) |
| Genesis vision (perceive the product image) | gpt-4o | SAP AI Core |
| Embeddings (dedup / lesson recall) | text-embedding-3-small | SAP AI Core |
| Voice (Tour / Guide / Intro) | OpenAI tts-1 **nova** | OpenAI (cosmetic only — *not* the brain; cached) |

*Note: the CF `agent-ui` deployment is currently configured `MODEL_PROVIDER=genaihub` (gpt-4o via the BTP destination two-hop); the local rig runs Claude on AI Core. No out-of-pocket model spend either way — OpenAI is used only for the voice.*
