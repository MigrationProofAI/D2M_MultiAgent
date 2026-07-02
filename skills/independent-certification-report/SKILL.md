---
name: independent-certification-report
description: Render an independent, read-only end-of-session certification card: SAP objects created (BOMs, routings, production versions, PIRs), demand source, and full MRP cascade with BOM explosion quantities — the auditable sign-off for any genesis/Design-2-Make/MRP task.
when_to_trigger: Automatically at the close of any genesis / Design-2-Make / MRP task; also when user says "certification report", "sign-off summary", "independent report", "end of session summary", "what did MRP plan?", "show the cascade", "final result"
---

# independent-certification-report

Render a card from LIVE SAP data into the STRUCTURED-DATA panel (not just chat). The runtime does
NOT execute inline scripts, so YOU bind the data and the rendering goes through render_card.

## Invoke recipe
1. Call the sources named in MAPPING (run_mrp / get_material / get_bom) for the material + plant in play.
2. Bind the returned data into the SCHEMA shape using the MAPPING rules.
3. Build the card as HTML following the TEMPLATE layout (sections, colours, chips).
4. Call render_card(title=..., content=<the card HTML>). It surfaces in the Structured Data panel.

## SCHEMA.md

# Independent Certification Report — Data Schema

## From genesis / run_genesis response
| Field | Source |
|---|---|
| FG material number | .parent.material |
| FG description | .parent.description |
| Component materials[] | .components[].material, .type, .description |
| BOM ID (FG) | .bom.id |
| BOM IDs (sub-assy) | .subBoms[].id |
| Routing (FG) | .routing.group |
| Routing (sub-assy) | .subRoutings[].group |
| Production version (FG) | .productionVersion |
| PIR IDs | .pirs[].id |

## From create_demand response
| Field | Source |
|---|---|
| sales_order | .sales_order |
| demand_qty | caller parameter |

## From run_mrp response
| Field | Source |
|---|---|
| timestamp | .timestamp |
| plannedOrdersCreated | .run.plannedOrdersCreated |
| purchaseReqsCreated | .run.purchaseReqsCreated |
| errors | .run.errors |
| materials[] | .materials |
| mat | .materials[].mat |
| type | .materials[].type |
| label / description | .materials[].label |
| level | .materials[].level |
| proc | .materials[].proc (E=make, F=buy) |
| output | .materials[].output (planned_order / purchase_req) |
| exception | .materials[].exception (true = exception msg) |

## From read_routing / read_production_version / read_pir (verification pass)
| Field | Source |
|---|---|
| routing group | read_routing.group |
| production version | read_production_version.version |
| PIR number | read_pir.id |


## SKILL.md

# Independent Certification Report

After a SAP genesis + demand + MRP sequence completes, render a final, structured,
independent sign-off card that certifies what was built and what the planning system
has planned. This is the LAST step of any Design-2-Make / genesis task.

## Purpose
Provide an auditable, human-readable end-of-session report that answers three questions:
1. **What was built?** — The finished-good, sub-assemblies and components created in SAP.
2. **What was demanded?** — The sales order / demand document raised against the FG.
3. **What did MRP plan?** — The full multi-level planned cascade (planned orders + purchase reqs)
   with quantities driven by the BOM explosion.

This skill is INDEPENDENT — it reads only from already-returned tool responses in context.
It does NOT re-call MRP, re-read SAP, or modify anything.

## When to trigger
- Automatically at the close of any genesis / Design-2-Make / plant-extension + MRP task.
- When the user asks: "show the certification report", "sign-off summary", "what was the final result?",
  "independent report", "show what MRP planned", "end of session summary".

## Inputs (all already in context — do NOT re-call tools)
| Input | Source |
|---|---|
| FERT material number + description | genesis / create_material response |
| Plant | user request / genesis spec |
| BOM object list | genesis-verifier or get_bom response |
| Routing numbers | read_routing responses |
| Production version numbers | read_production_version responses |
| PIR numbers | read_pir / create_info_record responses |
| Sales order number | create_demand response |
| Demand quantity | create_demand call parameter |
| Planned orders created | run_mrp response |
| Purchase reqs created | run_mrp response |
| Errors | run_mrp response |
| BOM cascade materials[] | run_mrp response |
| MRP run timestamp | run_mrp response |

## Procedure
1. Gather all inputs from context (responses already in the conversation).
2. Derive component quantities from the BOM explosion:
   - Level 0 (FERT): qty = demand_qty
   - Level 1 components: qty = demand_qty × qty_per
   - Level 2 sub-components: qty = (parent level-1 qty) × qty_per
3. Populate the TEMPLATE below with live values.
4. Call `render_card` as the FINAL step.

## Output emoji / colour legend
| Symbol | Meaning |
|---|---|
| ✅ | Confirmed / created successfully |
| 🟦 | Planned Order — in-house manufactured (FERT / HALB) |
| 🟨 | Purchase Requisition — bought-out (HAWA) |
| ⚠️ | Exception message — expected for fresh genesis with zero stock |
| ❌ | Error — investigate |

## TEMPLATE (populate and render via render_card)

```markdown
## ✅ Independent Certification Report
### {MATERIAL_DESC} ({MATERIAL_NO}) — Plant {PLANT}

---

### 1. SAP Objects Created

| Object | SAP ID | Status |
|---|---|---|
| Finished Good (FERT) | {FG_MAT} | ✅ Confirmed |
{COMPONENT_ROWS}
| BOM — {FG_MAT} | {BOM_FG_ID} | ✅ Confirmed |
{BOM_SUBASSY_ROWS}
| Routing — {FG_MAT} | {ROUTING_FG} | ✅ Confirmed |
{ROUTING_SUBASSY_ROWS}
| Production Version — {FG_MAT} | {PV_FG} | ✅ Confirmed |
{PV_SUBASSY_ROWS}
{PIR_ROWS}

---

### 2. Demand

| Field | Value |
|---|---|
| Sales Order | **{SALES_ORDER}** |
| Material | {FG_MAT} — {MATERIAL_DESC} |
| Quantity | **{DEMAND_QTY} EA** |
| Plant | {PLANT} |

---

### 3. MRP Cascade (MD02 Multi-Level)

**Run timestamp:** {TIMESTAMP}

| Output | Count |
|---|---|
| 🟦 Planned Orders Created | **{PLANNED_ORDERS}** |
| 🟨 Purchase Requisitions Created | **{PURCH_REQS}** |
| ❌ Errors | **{ERRORS}** |

#### Planned Cascade — BOM Explosion

| Lvl | Material | Description | Type | MRP Output | Qty Planned |
|---|---|---|---|---|---|
{CASCADE_ROWS}

---

### 4. Next Steps

- 🟦 **Planned Orders** → Planner converts to **Production Orders** in CO01/MD04
- 🟨 **Purchase Reqs** → Purchasing converts to **Purchase Orders** in ME21N / ME57
- ⚠️ Exceptions shown above are **expected** for a fresh genesis (zero stock on hand); planner reviews in **MD04**
{ERROR_BLOCK}
```

## Row templates

**COMPONENT_ROWS** (one per HALB/HAWA in scope):
`| {type} Component — {desc} | {mat_no} | ✅ Confirmed |`

**BOM_SUBASSY_ROWS** (one per HALB with its own BOM):
`| BOM — {halb_mat} ({desc}) | {bom_id} | ✅ Confirmed |`

**ROUTING_SUBASSY_ROWS** / **PV_SUBASSY_ROWS** — same pattern for each HALB.

**PIR_ROWS** (one per HAWA component):
`| PIR — {desc} ({mat_no}) | {pir_id} | ✅ Confirmed |`

**CASCADE_ROWS** (one per material in run_mrp materials[]):
`| {lvl_dots}{lvl} | **{mat}** | {desc} | {type} | {emoji} {output_label} {exception_flag} | {qty} EA |`
- lvl_dots: `.` per sub-level (level 1 = nothing, level 2 = `.`, level 3 = `..`)
- output_label: `Planned Order` or `Purchase Req`
- exception_flag: ` ⚠️` if exception:true, else blank

**ERROR_BLOCK** — only include if ERRORS > 0:
`> ❌ MRP Errors detected — review error messages above and resolve before converting orders.`
Omit entirely if ERRORS = 0.

## render_card call
- **title:** `Independent Certification Report — {MATERIAL_NO} @ Plant {PLANT}`
- **subtitle:** `{PLANNED_ORDERS} planned orders · {PURCH_REQS} purchase reqs · {ERRORS} errors · {TIMESTAMP}`
- **content:** the populated template above

## Notes
- If `create_demand` was not called in this session, set SALES_ORDER = `N/A` and DEMAND_QTY = `existing requirements`.
- If genesis-verifier was already run and returned GAPS, note any MISSING items in Section 1 with ⚠️ instead of ✅.
- Do NOT re-run any tools. This is a read-only render from context.

