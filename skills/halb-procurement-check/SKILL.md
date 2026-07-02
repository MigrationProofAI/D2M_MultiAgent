---
name: halb-procurement-check
description: After genesis/plant extension, verify every HALB has ProcurementType=E (In-House Production); fix any F defaults, re-run MRP, and render a traffic-light verification card
when_to_trigger: after run_genesis, after enable_plant_production, after HALB extend_to_plant, when MRP raises wrong PurchReqs for HALBs, HALB not planning correctly, HALB procurement type check
---

# halb-procurement-check

Render a card from LIVE SAP data into the STRUCTURED-DATA panel (not just chat). The runtime does
NOT execute inline scripts, so YOU bind the data and the rendering goes through render_card.

## Invoke recipe
1. Call the sources named in MAPPING (run_mrp / get_material / get_bom) for the material + plant in play.
2. Bind the returned data into the SCHEMA shape using the MAPPING rules.
3. Build the card as HTML following the TEMPLATE layout (sections, colours, chips).
4. Call render_card(title=..., content=<the card HTML>). It surfaces in the Structured Data panel.

## SKILL.md

# SKILL: halb-procurement-check

## Purpose
After any `run_genesis`, `enable_plant_production`, or manual HALB creation, verify that **every HALB component has `ProcurementType = E` (In-House Production)** at the target plant.  
If any HALB has `ProcurementType = F` (External), MRP will raise **Purchase Requisitions** instead of **Planned Orders** — completely defeating the purpose of a semi-finished make item.

---

## When to Trigger
- After `run_genesis` completes (confirm=true)
- After `enable_plant_production` completes (confirm=true)
- After any manual `extend_to_plant` for an HALB material
- Whenever a user reports "MRP raised PurchReqs for my HALB" or "HALB not planning correctly"
- As part of the post-genesis verification checklist

---

## Steps

### 1. Identify all HALB components in scope
From the genesis spec or BOM, collect every material with `type = HALB`.

### 2. Read each HALB's plant MRP data
Call `read_mrp_material(material=<halb_id>, plant=<plant>)` for each HALB.  
Check the `ProcurementType` field:
- ✅ `E` = In-House Production → correct, no action
- ❌ `F` = External → **must fix**
- ❌ `X` = Both → acceptable only if explicitly intended

### 3. Fix any HALB with ProcurementType ≠ E
Call `extend_to_plant` with the HALB's material type to re-push the plant/valuation view and set the correct procurement type:
```
extend_to_plant(
  material = <halb_id>,
  plant    = <plant>,
  product_type = "HALB"
  confirm  = false   ← preview first
)
```
Review the preview, then re-run with `confirm=true`.

### 4. Re-run MRP after all fixes
Once all HALBs are corrected, run:
```
run_mrp(
  material      = <fert_id>,
  plant         = <plant>,
  multi_level   = true,
  planning_mode = "3",   ← delete & recreate clears stale PurchReqs
  confirm       = true
)
```

### 5. Verify the cascade
Call `read_mrp_tree(material=<fert_id>, plant=<plant>)` and confirm:
- FERT → 🔵 Planned Order
- Every HALB → 🔵 Planned Order
- Every HAWA/ROH → 📋 Purchase Req

---

## Render a Verification Card
After verification, render a card using `render_card` with:
- Title: `HALB Procurement Type Check — <FERT material> @ Plant <plant>`
- A table of every HALB showing: Material | Description | Proc Type | Status
- Traffic-light status: ✅ E (correct) | ❌ F (wrong — fixed) | ⚠️ X (check intent)
- MRP re-run summary: Planned Orders Created, PurchReqs Created, Errors

---

## LESSON (from session 2026-06-30)
Root cause of the original failure: `extend_to_plant` defaulted HALB plant views to `ProcurementType = F`.  
SAP defaulted it to External because the plant view was created without explicitly asserting `E`.  
Fix: always pass `product_type = HALB` to `extend_to_plant` so the valuation class and procurement type are set correctly for a made item.

---

## Key SAP Rule
> **HALBs are MADE items. Made items must have `ProcurementType = E`.  
> `F` on an HALB is always a data defect. Fix it before MRP runs.**

