---
name: mrp-plant-extension-lessons
description: API lessons: extend_to_plant silently sets ND, update_material cannot patch plant MRP fields, MRPType=PD requires MRPResponsible, extend_to_plant ignores mrp_controller — always use enable_plant_production for active planning
when_to_trigger: extend_to_plant, enable_plant_production, update_material MRP fields, MRPType PD, MRP controller, no purchase reqs, no planned orders after extend, plant extension MRP, DISPO controller missing
---

# mrp-plant-extension-lessons

Render a card from LIVE SAP data into the STRUCTURED-DATA panel (not just chat). The runtime does
NOT execute inline scripts, so YOU bind the data and the rendering goes through render_card.

## Invoke recipe
1. Call the sources named in MAPPING (run_mrp / get_material / get_bom) for the material + plant in play.
2. Bind the returned data into the SCHEMA shape using the MAPPING rules.
3. Build the card as HTML following the TEMPLATE layout (sections, colours, chips).
4. Call render_card(title=..., content=<the card HTML>). It surfaces in the Structured Data panel.

## SKILL.md

# mrp-plant-extension-lessons

Captured API lessons from the Bicycle BOM genesis session (2026-06-26). Apply these BEFORE calling extend_to_plant, update_material, or enable_plant_production.

---

## LESSON 1 — extend_to_plant silently sets MRPType=ND

**Symptom:** After calling `extend_to_plant`, sub-level components have no planned orders or purchase reqs after MRP.

**Root cause:** `extend_to_plant` defaults every material's MRP type to `ND` (no planning). It does NOT set `PD` unless explicitly told to — and even then it does not accept `mrp_controller`.

**Fix:** Use `enable_plant_production` (not `extend_to_plant`) whenever you want a material to be **actively planned** at a plant. `enable_plant_production` sets `MRPType=PD` + `MRPResponsible` (controller) in a single grounded call.

---

## LESSON 2 — update_material cannot patch plant-level MRP fields

**Symptom:** Calling `update_material` with `{MRPType: "PD"}` returns an error (M3/069 or silent no-op).

**Root cause:** `MRPType` and `MRPResponsible` live in the **plant view** (`A_ProductPlant`), not in the material header (`A_Product`). `update_material` patches the header only.

**Fix:** Use `enable_plant_production` with `mrp_type=PD` + `mrp_controller=<grounded>` to write plant-level MRP fields.

---

## LESSON 3 — MRPType=PD requires MRPResponsible (mandatory pair)

**Symptom:** Setting `MRPType=PD` without `MRPResponsible` raises SAP error M3/069: "MRP controller is required for MRP type PD".

**Root cause:** SAP enforces that any active MRP type (PD, MK, etc.) must have a named MRP controller (DISPO) from the plant's valid controller table (T024D).

**Fix:** Always call `get_valid_mrp_controllers(plant)` first, then pass both `mrp_type=PD` AND `mrp_controller=<grounded value>` together. Never set one without the other.

---

## LESSON 4 — extend_to_plant does not accept mrp_controller parameter

**Symptom:** Passing `mrp_controller` to `extend_to_plant` is silently ignored or rejected.

**Root cause:** `extend_to_plant` is a LOW-LEVEL tool that only handles plant + valuation views. It has no parameter for MRP controller.

**Fix:** To extend a material AND set an MRP controller in one step, use `enable_plant_production`. If you only need a valuation/plant view with no planning (ND), then `extend_to_plant` is fine.

---

## Quick Decision Table

| Goal | Tool to Use |
|---|---|
| Extend whole assembly + planning + BOM + routing + PV | `enable_plant_production` |
| Extend a single material, no planning needed (ND) | `extend_to_plant` |
| Set MRPType=PD + MRP controller on existing plant view | `enable_plant_production` |
| Patch a header-level field (e.g. CountryOfOrigin) | `update_material` |
| Patch a plant-level MRP field | `enable_plant_production` (NOT `update_material`) |

