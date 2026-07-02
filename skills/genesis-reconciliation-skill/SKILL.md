---
name: genesis-reconciliation-skill
description: Render a Final Object Count Reconciliation scorecard (Planned vs Created vs Result) after any run_genesis call — includes HALB classification rule enforcement
when_to_trigger: after run_genesis, genesis reconciliation, object count, planned vs created, HALB classification check, before any genesis commit
---

# genesis-reconciliation-skill

Render a card from LIVE SAP data into the STRUCTURED-DATA panel (not just chat). The runtime does
NOT execute inline scripts, so YOU bind the data and the rendering goes through render_card.

## Invoke recipe
1. Call the sources named in MAPPING (run_mrp / get_material / get_bom) for the material + plant in play.
2. Bind the returned data into the SCHEMA shape using the MAPPING rules.
3. Build the card as HTML following the TEMPLATE layout (sections, colours, chips).
4. Call render_card(title=..., content=<the card HTML>). It surfaces in the Structured Data panel.

## HALB-RULE.md

# HALB Classification Rule — MANDATORY Pre-Genesis Check

## The Rule
**NEVER create a material as HALB (semi-finished) unless BOTH of the following are true:**

| Condition | Required? | Check |
|---|---|---|
| 1. The part has a defined Bill of Material (BOM) with child components | ✅ MANDATORY | Does it have sub-parts that are assembled/fabricated together? |
| 2. There is an internal manufacturing / value-add process (routing operation) performed on it | ✅ MANDATORY | Is there machining, welding, assembly, painting, or any shop-floor operation done IN-HOUSE? |

## If EITHER condition is false → reclassify:

| Situation | Correct Type |
|---|---|
| Part is bought from a vendor, no internal process | **HAWA** (Trading Good) |
| Part is a raw material input (sheet, rod, bar) | **ROH** (Raw Material) |
| Part is fabricated in-house WITH a BOM AND routing | **HALB** (Semi-finished) ✅ |
| Part is the top-level finished product | **FERT** (Finished Good) ✅ |

## Why This Matters
- An HALB without a BOM is an orphan — MRP cannot explode it, costing cannot roll up through it.
- An HALB without a routing has no manufacturing process — it cannot be produced, only procured.
- Creating HALB for bought-out parts inflates object counts, confuses procurement, and breaks MRP.

## Enforcement in Genesis
Before calling `run_genesis` or `build_material_payload` with `product_type=HALB`:
1. **Ask:** Does this part have child components (BOM)?
2. **Ask:** Does this part go through an internal operation (routing)?
3. If NO to either → **reclassify to HAWA or ROH** and add a PIR instead.
4. Only proceed as HALB if YES to BOTH.

## Examples from Autonomous Robot Vehicle Session
| Part | Initially Classified | Correct Classification | Reason |
|---|---|---|---|
| Front Sensor Compartment | HALB ❌ | HAWA | Bought enclosure, no internal BOM or process defined |
| Rear Sensor Compartment | HALB ❌ | HAWA | Same as above |
| Left Spindle | HALB ❌ | HAWA | No sub-components or machining ops specified |
| Right Spindle | HALB ❌ | HAWA | Same as above |
| Chassis Frame | HALB ❌ | HAWA or ROH | Sheet metal/fabricated but no BOM children defined |

## Session Lesson (verbatim)
> "Sorry we do not create HALB if they don't have a BOM and have any internal process
> to add value on bought out items. Let's make sure we put this as part of knowledge."

