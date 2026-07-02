---
name: halb-mrp-settings-verifier
description: After any genesis/BOM/plant-extension write, verify every HALB has ProcurementType=E (in-house) and MRPType=PD — and fix + re-run MRP if not.
when_to_trigger: After run_genesis, enable_plant_production, or any BOM write involving HALBs; when user says "HALB not planned", "HALBs generating PRs instead of planned orders", "wrong proc type", "HALB procurement type", "HALB MRP type"
---

# halb-mrp-settings-verifier

Render a card from LIVE SAP data into the STRUCTURED-DATA panel (not just chat). The runtime does
NOT execute inline scripts, so YOU bind the data and the rendering goes through render_card.

## Invoke recipe
1. Call the sources named in MAPPING (run_mrp / get_material / get_bom) for the material + plant in play.
2. Bind the returned data into the SCHEMA shape using the MAPPING rules.
3. Build the card as HTML following the TEMPLATE layout (sections, colours, chips).
4. Call render_card(title=..., content=<the card HTML>). It surfaces in the Structured Data panel.

## MAPPING.md

# Field Mapping — HALB MRP Settings

## A_ProductPlant (OData entity)
| Field | Value | Meaning |
|---|---|---|
| ProcurementType | "E" | In-house manufacture (make) |
| ProcurementType | "F" | External procurement (buy) — WRONG for HALB |
| ProcurementType | "X" | Both (special cases only) |

## A_ProductPlantMRPArea (OData entity)
| Field | Value | Meaning |
|---|---|---|
| MRPType | "PD" | MRP-driven planning — REQUIRED for make materials |
| MRPType | "ND" | No planning — MRP ignores this material |
| MRPResponsible | e.g. "001" | MRP Controller — mandatory with PD |

## Keys
- A_ProductPlant: {Product, Plant}
- A_ProductPlantMRPArea: {Product, Plant, MRPArea} — MRPArea = Plant code

## MRP Output by ProcurementType
| ProcType | MRP Output | Correct for |
|---|---|---|
| E | Planned Order | FERT, HALB (make) |
| F | Purchase Requisition | HAWA, ROH (buy) |


## SKILL.md

# SKILL: halb-mrp-settings-verifier

## Purpose
After ANY genesis / BOM write / plant-extension that involves HALB (semi-finished) materials, verify — and fix if needed — that every HALB has:
1. **ProcurementType = E** (in-house manufacture) — NOT F (external/purchase)
2. **MRPType = PD** (MRP-driven planning) — NOT ND (no planning)
3. **MRP Controller set** (required whenever MRPType = PD)

If any HALB has ProcurementType = F, MRP will raise **purchase requisitions** instead of **planned orders**, breaking the make cascade.

---

## When to Trigger
- After `run_genesis` / `enable_plant_production` completes
- After any BOM write involving HALB components
- After any plant extension of an assembly
- When user says "HALB procurement type", "HALB not planned", "wrong proc type", "HALBs generating PRs instead of planned orders"
- As part of the post-genesis verification chain (after bom-precondition / genesis-verifier)

---

## Steps

### 1. Identify all HALBs in the assembly
- From the BOM (get_bom) or the genesis spec, collect every material with type = HALB.

### 2. Read the plant view for each HALB
- Call `get_material(material_id, full=true)` for each HALB.
- Check the A_ProductPlant view fields:
  - `ProcurementType` → must be **"E"**
  - `MRPType` → must be **"PD"** (or the agreed planning type)
  - `MRPResponsible` (MRP Controller) → must be **non-blank**

### 3. Report findings
Render a table:

| Material | Description | ProcType | MRPType | MRP Controller | Status |
|---|---|---|---|---|---|
| 12338 | CF Frame Sub-Assy | E | PD | 001 | ✅ OK |
| 12339 | Motor Mount Sub-Assy | F | ND | — | ❌ FIX |

### 4. Fix any gaps (with confirm gate)
For each HALB that fails:

**a) Fix ProcurementType → E:**
```
change_material(
  entity="A_ProductPlant",
  keys={"Product": "<mat>", "Plant": "<plant>"},
  fields={"ProcurementType": "E"},
  confirm=false  -- preview first
)
```

**b) Fix MRPType → PD + MRP Controller:**
```
change_material(
  entity="A_ProductPlantMRPArea",
  keys={"Product": "<mat>", "Plant": "<plant>", "MRPArea": "<plant>"},
  fields={"MRPType": "PD", "MRPResponsible": "<controller>"},
  confirm=false
)
```
Controller must be grounded from `get_valid_mrp_controllers(plant)` — never guess.

**c) Confirm gate:** Always preview (confirm=false) first, show the user the diff, then re-run with confirm=true only after explicit approval.

### 5. Re-run MRP after fixing
- Run `run_mrp(material=<FERT>, multi_level=true, planning_mode="3", confirm=true)`
- Verify HALBs now produce **planned_order** (not purchase_req) in the cascade.

---

## Key Facts (Lessons Learned)
- SAP defaults HALBs to **ProcurementType = F** at creation — this is almost always wrong for made sub-assemblies.
- `extend_to_plant` silently inherits the wrong type if the source plant had F.
- `run_genesis` may also produce HALBs with F — always verify post-genesis.
- A HALB with ProcType=F AND a routing/production version is contradictory — MRP will still raise a PR, wasting the routing.
- MRPType=ND means MRP ignores the material entirely — even with a BOM and routing, no planned order is created.
- MRPType=PD requires MRPResponsible — if blank, SAP may silently reject or ignore planning.

---

## Checklist (Post-Fix)
- [ ] All HALBs: ProcurementType = **E**
- [ ] All HALBs: MRPType = **PD**
- [ ] All HALBs: MRP Controller set
- [ ] MRP re-run: HALBs output = **planned_order** (not purchase_req)
- [ ] No errors in MRP run

