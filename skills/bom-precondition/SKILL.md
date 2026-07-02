---
name: bom-precondition
description: Preconditions and completeness checklist for BOM/genesis writes — plant extension, routings, production versions, PIRs, prices, and CountryOfOrigin policy
when_to_trigger: before any BOM create, genesis run, plant extension, or Design-to-Make build; when creating materials for a multi-level assembly
---

# bom-precondition

Render a card from LIVE SAP data into the STRUCTURED-DATA panel (not just chat). The runtime does
NOT execute inline scripts, so YOU bind the data and the rendering goes through render_card.

## Invoke recipe
1. Call the sources named in MAPPING (run_mrp / get_material / get_bom) for the material + plant in play.
2. Bind the returned data into the SCHEMA shape using the MAPPING rules.
3. Build the card as HTML following the TEMPLATE layout (sections, colours, chips).
4. Call render_card(title=..., content=<the card HTML>). It surfaces in the Structured Data panel.

## SKILL.md

# bom-precondition (promoted lessons)

Apply these before the write:

- **promoted L-52d4017f (2026-06-16)**: No this is a learning moment to be updated in the skill. Before we can have the BOM for a given plant the FG as well as all components must be extended to that plant first

- **promoted L-multilevel-spec (2026-06-29)**: The genesis SPEC itself must be a multi-level TREE, planned UPFRONT — do not emit a flat parent+components list and rely on the Board/heal to backfill the HALB sub-structure. Each made (HALB) component must carry its own `components` (its raws/sub-parts) and `routing` in the spec; `run_genesis` then builds that HALB's BOM + routing + production version in the same pass. Nest each bought part under the sub-assembly it belongs to. Mark inferred sub-parts `"inferred": true` so the preview/Board can vet them (the "infer + flag" rule).

- **promoted L-bicycle-completeness (2026-06-17)**: A full Design-to-Make genesis for a multi-level assembly requires ALL of the following — not just the FERT level:
  1. **Materials** — FERT + all HALB + all HAWA created with correct types and product groups.
  2. **BOMs** — One BOM per *made* parent (FERT + every HALB). HAWA items are leaves — no BOM needed.
  3. **Routings** — One routing per *made* material (FERT **and** every HALB). Each HALB that has assembly steps needs its own routing, not just the finished good.
  4. **Production Versions** — One production version per *made* material (FERT + every HALB), binding BOM alt + routing.
  5. **PIRs (Purchase Info Records)** — One PIR per HAWA/bought-out component, with vendor and price. Web-sourced prices must be *committed*, not just previewed.
  6. **Standard Prices** — Valuation prices on HAWA materials must be written to SAP (not left as preview).
  7. **CountryOfOrigin** — Must be set on all materials per policy; do not leave blank.
