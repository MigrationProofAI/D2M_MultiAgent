# Design2Make — Architecture

> A clean-room, multi-agent rig that turns a product (photo · sketch · description) into real,
> **verified** SAP master data **and** the plan to make it. This document mirrors the in-app
> **🏗 Architecture** explainer (source of truth: `Design2Make_R00763/frontend/src/App.jsx` →
> `ARCH`, `ARCH_DETAIL`, `ArchDiagram`).

## Layered stack

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ EXPERIENCE      React UI · WebSocket · live reasoning / activity / data        │
│                 · persisted for replay                                          │
├──────────────────────────────────────────────────────────────────────────────┤
│ MODEL           Claude on SAP AI Core · vision for genesis · voice via OpenAI  │
│                 only (no out-of-pocket model spend)                             │
├──────────────────────────────────────────────────────────────────────────────┤
│ AGENTS · 10     Maker · Verifier · Conductor · Board ×5 · Chair · Guide         │
│                 bounded; authority enforced at dispatch                         │
├──────────────────────────────────────────────────────────────────────────────┤
│ ORCHESTRATION   sequential · parallel (board) · loop (verify→heal) · hybrid     │
├──────────────────────────────────────────────────────────────────────────────┤
│ TOOLS · MCP     typed contracts (CSRF · keys · deep-inserts · preview→commit)  │
│                 → 7 SAP OData services + 2 RFC functions                        │
├──────────────────────────────────────────────────────────────────────────────┤
│ GROUNDING       ConfigGraph codebook + plant config · skills ·                  │
│ & MEMORY        learning (lessons → promoted skills)                            │
├──────────────────────────────────────────────────────────────────────────────┤
│ SAP S/4HANA     system of record — every write real, confirmed, re-verified    │
└──────────────────────────────────────────────────────────────────────────────┘
```

The pipeline within it:
**📷 product → 🛠 Maker ⇄ 🛡 Verifier → 🗄 SAP → 📈 Plan (PIR · MRP)** — under the 🏛 Board + 🎼 Conductor,
with 🙋 Genesis-preview & human-in-the-loop on every write.

## Narration script (12 scenes)

1. Design2Make is a clean-room, multi-agent rig for SAP master data. It's built in layers — from the screen you see down to the system of record. Here's how it fits together.
2. **(Experience)** At the top, the experience layer: a React app over a WebSocket that streams every agent's reasoning, actions and results into live panels — and persists them, so any session can be replayed.
3. **(Model)** Beneath it, the model layer. The agents reason on Claude, running on SAP AI Core, with a vision model for reading product images. The only outside call is the voice you're hearing.
4. **(Agents)** Then the agent layer: ten bounded agents — a Maker, a Verifier, a Conductor, a five-seat Board, a Chair and a Guide.
5. **(Agents — drill-down ▼)** Authority isn't a suggestion — it's enforced at dispatch. The Maker holds every write tool; the Verifier gets a read-only set and not even a search, so it can only certify the exact objects it was handed; the Board reviews in pure reasoning; the Guide only explains. Each draws on focused skills — material-create, bom-precondition, codebook-grounding, the genesis-verifier.
6. **(Orchestration)** The Conductor orchestrates them in four shapes — sequential, parallel for the board, a capped loop for build-and-verify, and hybrids of these.
7. **(Tools)** Every action runs through the tool layer: typed MCP contracts that wrap real SAP services. The contracts own CSRF, keys, deep inserts and preview-then-commit, so the agents never touch raw OData by hand.
8. **(Tools — OData drill-down ▼)** Each tool wraps a specific SAP OData service: materials on API_PRODUCT_SRV, BOMs on the bill-of-material service, routings on API_PRODUCTION_ROUTING, info records and price conditions on theirs, demand on the planned-independent-requirement service, and the MD04 read on the MRP-materials service.
9. **(Tools — RFC drill-down ▼)** And where OData can't reach, we go straight to RFC. BAPI material planning runs MRP; a custom function — Z-D-2-M prod-vers maintain — writes the production version into table M-K-A-L; and RFC read-table reads M-K-A-L and M-A-P-L back. Each lives in its own isolated server.
10. **(Grounding & memory)** Underneath, a grounding and memory layer keeps it honest: a config-graph codebook of the system's real codes and plant config, plus skills and a learning loop that turns mistakes into lessons, and lessons into promoted skills.
11. **(SAP)** And it all lands on one system of record — SAP S/4HANA — where every write is real, confirmed by a human, and independently re-verified.
12. **(all layers lit)** Layers from screen to system, ten bounded agents, four orchestration shapes, typed contracts over seven OData services and two RFC functions. That's the architecture of Design2Make.

## Drill-down — Agents · authority & skills (scene 5)

| Agent | Authority (tool-set) | Skills |
|---|---|---|
| **Maker** | all write tools (no `search_materials`) | material-create · bom-precondition · codebook-grounding |
| **Verifier** | read-only set — NO search; certifies only what it's handed | genesis-verifier · plant-view-verifier |
| **Conductor** | sequential · parallel · loop · hybrid | — |
| **Board ×5** | Engineering · Procurement · Compliance · Finance · Planning — pure reasoning | codebook-consult |
| **Chair** | synthesises the panel into one go / no-go | — |
| **Guide** | explain only — binds no SAP tools | — |

## Drill-down — MCP tools → SAP OData services (scene 8)

| OData service | Tools | Entity sets |
|---|---|---|
| `API_PRODUCT_SRV` | get/create/update/change_material · extend_to_plant | A_Product · A_ProductPlant · A_ProductValuation |
| `API_BILL_OF_MATERIAL_SRV;v=2` | get/create/change_bom · add/remove_component | MaterialBOM · MaterialBOMItem |
| `API_PRODUCTION_ROUTING` | get_routing · set_routing_operation · change_routing | ProductionRouting · ProductionRoutingOperation |
| `API_INFORECORD_PROCESS_SRV` | read_pir · create_info_record · set_supplier_terms | A_PurchasingInfoRecord · A_PurgInfoRecdOrgPlantData |
| `API_PURGPRCGCONDITIONRECORD_SRV` | read/create/change_cost_condition · set_condition_price | A_PurgPrcgConditionRecord |
| `API_PLND_INDEP_RQMT_SRV` (:8003) | create_demand · read_demand | PlannedIndepRqmt · to_PlndIndepRqmtItem (VSF/00) |
| `API_MRP_MATERIALS_SRV_01` (:8004) | read_mrp_list · read_mrp_material | SupplyDemandItems (MD04) · A_MRPMaterial |

## Drill-down — MCP tools → RFC call-outs (scene 9)

| Server | RFC function / BAPI | Backs |
|---|---|---|
| `:8001` | `BAPI_MATERIAL_PLANNING` (+ `BAPI_TRANSACTION_COMMIT`) | run_mrp — the planned cascade |
| `:8002` | `ZD2M_PROD_VERS_MAINTAIN` | create/read production version → table **MKAL** |
| read-back | `RFC_READ_TABLE` | read_routing → **MAPL** · read_production_version → **MKAL** |

## Server topology

| Port | Server | Transport | Backs |
|---|---|---|---|
| `:9000` | `web.py` (FastAPI) | HTTP + WebSocket | the rig + UI; in-process OData (sap.py / make.py) |
| `:8001` | `sap_planning_mcp.py` | SSE / NWRFC | MRP run (BAPI_MATERIAL_PLANNING) |
| `:8002` | `sap_prodvers_mcp.py` | SSE / NWRFC | production version + routing read (ZD2M_PROD_VERS_MAINTAIN, RFC_READ_TABLE) |
| `:8003` | `mcp-plndindepreqmt` | streamable-http | PIR demand (API_PLND_INDEP_RQMT_SRV) |
| `:8004` | `mcp-mrp` | streamable-http | MD04 read (API_MRP_MATERIALS_SRV_01) |
