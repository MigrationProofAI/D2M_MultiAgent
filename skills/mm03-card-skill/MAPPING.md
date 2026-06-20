# MM03 Card Skill — MAPPING

## How to populate the card

1. Call `get_material(material_id=<number>, full=true)` → returns the `A_Product` JSON.
2. Extract fields per SCHEMA.md.
3. Derive `material_type_desc` from `ProductType`:
   - FERT → Finished Product
   - HAWA → Trading Goods
   - ROH  → Raw Material
   - HALB → Semi-finished Product
   - DIEN → Service
   - *(other)* → show raw code
4. Checkbox fields: render ✅ if value is `true` / `"X"`, else ☐.
5. Empty / null fields: render as `—` (em-dash), never blank.
6. If `full=true` returns plant views, pick the first plant row for the plant summary strip.
7. Call `render_card(title, subtitle, content)` as the FINAL step.

## Title / Subtitle pattern
- title:    `MM03 — Display Material · {Product}`
- subtitle: `{ProductDescription} ({material_type_desc})`

## Trigger phrases
- "show MM03", "MM03 card", "display material", "material master card",
  "show material master", "MM03 for <material>", "display material <number>"
