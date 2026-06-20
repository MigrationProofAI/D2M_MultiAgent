---
name: codebook-grounding
description: Ground every coded field from the codebook (or the plant config) before writing — never default, guess, or omit a required coded field.
when_to_trigger: Any genesis or extension that sets coded fields — material/product group, MRP type, MRP controller, valuation class, price control, procurement type, availability check, storage location, etc.
verification: Every coded field in the proposed payload was looked up (list_allowed_values, or get_valid_* for plant config) and the chosen value is in the returned valid set.
---

# Ground coded fields — never guess

On the rig's own agent the strong model's SAP knowledge isn't there, so the discipline must replace
it. Before you propose ANY coded field, ground it.

1. **Look it up, choose from the valid set.** For every coded field, call `list_allowed_values(field)`
   and pick ONLY from the returned values. Never default, never guess, never omit a required coded
   field — guessing reaches SAP and comes back as a cryptic reject (M3/180, MG/172, a missing plant
   field).

2. **Use OData field names, not classic ones.** `ProductGroup` (not `MaterialGroup`), `MRPType`,
   `ProcurementType`, `ValuationClass`. If `list_allowed_values` says a name is "not a coded field",
   read the field list it returns and map to the correct OData name — do not loop on the classic name.

3. **MRP type implies a controller.** Use a *planning* MRP type (e.g. `PD`) when the material must be
   planned/procured at the plant — never `ND` (no planning) unless no-planning is explicitly intended.
   A planning MRP type **requires** an MRP controller; set one.

4. **Plant-specific values are NOT in the codebook — use the config tools.** Storage locations and
   valid MRP controllers are per-plant config, not flat domains:
   - storage location → `get_valid_storage_locations(plant)`
   - MRP controller   → `get_valid_mrp_controllers(plant)`
   Ground these from those tools for the *target plant*; never reuse another plant's value (e.g. a
   `171*` storage location belongs to plant 1710, not 1010) and never guess them.

5. **Preview, then confirm.** Show the grounded payload (which fields, which values, where each came
   from) and wait for explicit confirmation before writing.
