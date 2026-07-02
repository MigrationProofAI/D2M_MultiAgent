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
