---
name: mrp-type-pd-checklist
description: After any genesis/BOM/plant-extension write, verify ALL BOM materials (FERT+HALBs+HAWAs) have MRPType=PD + MRP Controller set — extend_to_plant silently defaults to ND which kills sub-level planning
when_to_trigger: after run_genesis, after enable_plant_production, after extend_to_plant, whenever MRP not generating purchase reqs, whenever sub-level planned orders missing, 'why no purchase reqs', 'MRP not planning components'
---

# mrp-type-pd-checklist

Render a card from LIVE SAP data into the STRUCTURED-DATA panel (not just chat). The runtime does
NOT execute inline scripts, so YOU bind the data and the rendering goes through render_card.

## Invoke recipe
1. Call the sources named in MAPPING (run_mrp / get_material / get_bom) for the material + plant in play.
2. Bind the returned data into the SCHEMA shape using the MAPPING rules.
3. Build the card as HTML following the TEMPLATE layout (sections, colours, chips).
4. Call render_card(title=..., content=<the card HTML>). It surfaces in the Structured Data panel.

## LESSONS.md

## Lessons Learned from Bicycle BOM Genesis (Session 2026-06)

### Lesson 1: extend_to_plant defaults to MRPType=ND
- **Impact:** All sub-BOM materials (HALBs + HAWAs) had MRP switched off silently
- **Detection:** MRP ran on FERT only; no planned orders or purchase reqs for components
- **Fix:** Use enable_plant_production (not extend_to_plant or update_material) to set PD+controller

### Lesson 2: update_material patches A_Product (header), not A_ProductPlant
- **Impact:** Cannot set MRPType or MRPResponsible via update_material
- **Error:** '400 Property MRPResponsible is invalid'
- **Fix:** Use enable_plant_production which PATCHes A_ProductPlant correctly

### Lesson 3: MRPType=PD requires MRPResponsible — they are a pair
- **Impact:** Setting PD without a controller causes SAP error M3/069
- **Valid controllers for plant 1710:** 001, 002, MZ3
- **Fix:** Always pass both mrp_type=PD AND mrp_controller=001 together

### Lesson 4: extend_to_plant does not accept mrp_controller parameter
- **Impact:** Cannot use extend_to_plant to set PD+controller in a single call
- **Error:** 'TypeError: extend_to_plant() got an unexpected keyword argument mrp_controller'
- **Fix:** Use enable_plant_production instead


## SKILL.md

# MRP Type PD Checklist Skill

## Purpose
After any genesis / BOM / plant-extension write, verify that EVERY material in the BOM tree (FERT + all HALBs + all HAWAs) has MRPType=PD and a valid MRP Controller set at the plant level. MRPType=ND (the default for `extend_to_plant`) means MRP is completely switched off for that material — no planned orders, no purchase reqs will ever be generated.

## When to Trigger
- After `run_genesis` completes
- After `enable_plant_production` completes
- After any `extend_to_plant` call where MRP planning is intended
- Whenever user asks 'why are no purchase reqs being generated' or 'MRP not planning sub-levels'

## The Lesson (Root Cause)
`extend_to_plant` tool defaults to `MRPType: ND` (No Planning) when no override is passed. Every HAWA and HALB extended via this tool will silently have MRP switched OFF. Only `enable_plant_production` (used for the FERT parent) correctly sets MRPType=PD.

## Fix Protocol
1. For each HALB and HAWA in the BOM tree, call `enable_plant_production` with `mrp_type=PD` and `mrp_controller=<valid controller for plant>`
2. Do NOT use `update_material` — MRPType and MRPResponsible live on `A_ProductPlant`, NOT `A_Product` (the header entity). update_material patches the header and will fail with 'Property MRPResponsible is invalid'
3. Do NOT use `extend_to_plant` with just `mrp_type=PD` — it does not accept `mrp_controller` as a parameter and SAP will reject PD without a controller (error M3/069: 'Enter the MRP controller')
4. `enable_plant_production` is the ONLY tool that correctly sets both MRPType + MRPResponsible on the plant sub-entity

## API Facts (grounded from $metadata)
- `MRPType` lives on: `A_ProductPlant`, `A_ProductPlantMRPArea`, `A_ProductSupplyPlanning`
- `MRPResponsible` lives on: `A_ProductPlant`, `A_ProductPlantMRPArea`, `A_ProductSupplyPlanning`
- Neither field is on `A_Product` (the header)
- When MRPType=PD, MRPResponsible is MANDATORY (SAP error M3/069)

## Checklist (run after any genesis/extension)
- [ ] FERT parent: MRPType=PD ✓ (set by enable_plant_production)
- [ ] Every HALB in BOM: MRPType=PD + MRPResponsible set
- [ ] Every HAWA in BOM: MRPType=PD + MRPResponsible set
- [ ] Verify by reading A_ProductPlant for each material
- [ ] Re-run MD02 (multi-level) AFTER all MRP types corrected

