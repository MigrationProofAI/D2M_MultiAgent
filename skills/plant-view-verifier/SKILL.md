---
name: plant-view-verifier
description: Verify every material in an assembly (FERT + all BOM components, recursively) has a valid plant view at a target plant — with MRP-type warnings and a remediation list — before any BOM/routing/PV write. Step 2 of the post-genesis verification chain.
when_to_trigger: after run_genesis confirmed, after genesis-verifier, post-genesis verification, do all components have plant views, verify plant extensions, material not extended to plant, plant view missing, check plant views before BOM, after enable_plant_production, before independent-certification-report
---

# plant-view-verifier

Render a card from LIVE SAP data into the STRUCTURED-DATA panel (not just chat). The runtime does
NOT execute inline scripts, so YOU bind the data and the rendering goes through render_card.

## Invoke recipe
1. Call the sources named in MAPPING (run_mrp / get_material / get_bom) for the material + plant in play.
2. Bind the returned data into the SCHEMA shape using the MAPPING rules.
3. Build the card as HTML following the TEMPLATE layout (sections, colours, chips).
4. Call render_card(title=..., content=<the card HTML>). It surfaces in the Structured Data panel.

## MAPPING.md

# plant-view-verifier — MAPPING

## Data sources → SCHEMA fields

| SCHEMA Field | Tool | Path in Response | Notes |
|---|---|---|---|
| material_id | get_material | .Material or .Product | |
| description | get_material | .ProductDescription or .MaterialName | |
| material_type | get_material | .MaterialType | FERT/HALB/HAWA/ROH |
| plant_view_exists | get_material full=true | Look for plant-keyed block e.g. to_Plant, PlantData, or any field containing the target plant code | true if found with matching plant |
| mrp_type | get_material plant data | .MRPType or .to_Plant[plant].MRPType | PD=active planning, ND=no planning, blank=missing |
| valuation_class | get_material | .ValuationClass or valuation view | |
| bom_level | derived | 0 for parent, 1 for direct BOM items, 2 for sub-BOM items | Walk get_bom recursively |

## BOM traversal
1. get_bom(parent, plant) → items list → collect component material numbers
2. For each HALB component, get_bom(component, plant) → sub-items
3. Stop at HAWA/ROH (leaf nodes, no BOM)
4. Deduplicate: if same material appears in multiple BOMs, verify once

## Status logic
- CONFIRMED: get_material returns plant-level data for the target plant (fields populated, not blank/null)
- MISSING: get_material returns no plant entry for target plant, or plant fields all blank
- Flag MRP_WARN (amber) if plant view exists but MRPType = ND (no planning — won't be MRP-planned)


## SCHEMA.md

# plant-view-verifier — SCHEMA

## Input
| Field | Source | Description |
|---|---|---|
| parent_material | User / search_materials | The top-level FERT assembly material number |
| plant | User | Target plant code (e.g. 1710) |

## Per-Material Record
| Field | Source | Description |
|---|---|---|
| material_id | get_material | SAP material number |
| description | get_material | Material description |
| material_type | get_material | FERT / HALB / HAWA / ROH |
| bom_level | derived | 0=FERT, 1=direct component, 2=sub-component |
| plant_view_exists | get_material | true if plant data for target plant found in response |
| mrp_type | get_material plant view | e.g. PD, ND, blank |
| valuation_class | get_material valuation view | e.g. 3000, 7920 |
| status | derived | CONFIRMED / MISSING |

## Summary
| Field | Derived | Description |
|---|---|---|
| total_materials | count | Total materials in scope |
| confirmed_count | count | Materials with valid plant view |
| missing_count | count | Materials without plant view |
| verdict | logic | PASS (missing=0) or FAIL (missing>0) |


## SKILL.md

# plant-view-verifier

## Purpose
Verify every material in an assembly (FERT + all BOM components, recursively) has a valid plant view at a target plant — with MRP-type warnings and a remediation list.

## When to trigger
- Automatically, as **Step 2 of the post-genesis verification chain**, after `genesis-verifier` completes and before `independent-certification-report`
- Any time `run_genesis(confirm=true)` or `enable_plant_production(confirm=true)` is committed
- *"Do all components have plant views?"*
- *"Verify plant extensions for [material] at plant [X]"*
- When a BOM/routing write fails with *'material not extended'*
- Before any BOM/routing/production-version write on a new plant

## Post-Genesis Verification Chain
```
 run_genesis(confirm=true)
        |
        v
 [1] genesis-verifier          ← BOMs, routings, PVs, PIRs exist?
        |
        v
 [2] plant-view-verifier       ← ALL materials plant-extended? MRP type OK?
        |
        v
 [3] independent-certification-report  ← Auditable sign-off card
```

## Steps
1. `get_bom` recursively on the FERT → HALBs → sub-components (full BOM tree)
2. `get_material(full=true)` on every node in the tree
3. Check for plant-level data block in the response
4. Flag missing plant views as ❌ MISSING (remediation required)
5. Flag MRP type ND as 🟡 MRP_WARN (plant view exists, but material won't be planned)
6. Output a colour-coded HTML card via `render_card()`
7. Provide exact `extend_to_plant` remediation calls for every MISSING item

## Output Card Sections
- **Header**: assembly material + plant + PASS / FAIL verdict chip
- **Summary strip**: total / confirmed / missing / MRP warnings
- **Detail table**: one row per material — level, type, plant view, MRP type, status chip
- **Remediation block**: exact `extend_to_plant` calls for MISSING items
- **MRP warning block**: ND materials + fix instruction (use `enable_plant_production`)

## Rules
- PASS only if: missing = 0 AND mrp_warnings = 0
- FAIL if: any material has no plant view
- WARN (not fail) if: plant view exists but MRP type = ND
- Cannot write — read-only verification only
- Feeds into `independent-certification-report` as a prerequisite step


## TEMPLATE.md

# plant-view-verifier — CARD TEMPLATE

```html
<div style="font-family:Arial,sans-serif;max-width:900px">

  <!-- HEADER -->
  <div style="background:#1a3c5e;color:white;padding:12px 16px;border-radius:6px 6px 0 0;display:flex;justify-content:space-between;align-items:center">
    <span style="font-size:16px;font-weight:bold">🏭 Plant View Verification</span>
    <span style="font-size:13px">{{parent_material}} — {{parent_description}} @ Plant {{plant}}</span>
    <span style="background:{{verdict_colour}};padding:4px 12px;border-radius:4px;font-weight:bold">{{verdict}}</span>
  </div>

  <!-- SUMMARY STRIP -->
  <div style="background:#f0f4f8;padding:10px 16px;display:flex;gap:24px;border-bottom:1px solid #ccc">
    <span>📦 <strong>{{total_materials}}</strong> materials in scope</span>
    <span style="color:green">✅ <strong>{{confirmed_count}}</strong> confirmed</span>
    <span style="color:{{missing_colour}}">❌ <strong>{{missing_count}}</strong> missing plant view</span>
    <span style="color:orange">⚠️ <strong>{{mrp_warn_count}}</strong> MRP type = ND (no planning)</span>
  </div>

  <!-- MATERIAL TABLE -->
  <table style="width:100%;border-collapse:collapse;font-size:13px">
    <thead>
      <tr style="background:#2c5f8a;color:white">
        <th style="padding:8px;text-align:left">Level</th>
        <th style="padding:8px;text-align:left">SAP#</th>
        <th style="padding:8px;text-align:left">Description</th>
        <th style="padding:8px;text-align:center">Type</th>
        <th style="padding:8px;text-align:center">Plant View</th>
        <th style="padding:8px;text-align:center">MRP Type</th>
        <th style="padding:8px;text-align:center">Val. Class</th>
        <th style="padding:8px;text-align:center">Status</th>
      </tr>
    </thead>
    <tbody>
      <!-- repeat per material, alternating row colour -->
      <tr style="background:{{row_colour}}">
        <td style="padding:6px 8px">L{{bom_level}}</td>
        <td style="padding:6px 8px;font-family:monospace">{{material_id}}</td>
        <td style="padding:6px 8px">{{description}}</td>
        <td style="padding:6px 8px;text-align:center"><span style="background:#e8f4fd;padding:2px 6px;border-radius:3px">{{material_type}}</span></td>
        <td style="padding:6px 8px;text-align:center">{{plant_view_chip}}</td>
        <td style="padding:6px 8px;text-align:center">{{mrp_type_chip}}</td>
        <td style="padding:6px 8px;text-align:center">{{valuation_class}}</td>
        <td style="padding:6px 8px;text-align:center"><strong style="color:{{status_colour}}">{{status}}</strong></td>
      </tr>
    </tbody>
  </table>

  <!-- REMEDIATION SECTION (only if missing > 0) -->
  <!-- {{#if missing_count > 0}} -->
  <div style="background:#fff3cd;border:1px solid #ffc107;padding:12px 16px;margin-top:8px;border-radius:4px">
    <strong>⚠️ Remediation Required</strong>
    <p style="margin:6px 0 4px">The following materials must be extended to plant {{plant}} before any BOM, routing, or production version write:</p>
    <ul>
      <!-- {{#each missing_materials}} -->
      <li><code>{{material_id}}</code> — {{description}} ({{material_type}}) → call <code>extend_to_plant(material="{{material_id}}", plant="{{plant}}")</code></li>
      <!-- {{/each}} -->
    </ul>
  </div>
  <!-- {{/if}} -->

  <!-- MRP WARNING (only if mrp_warn > 0) -->
  <!-- {{#if mrp_warn_count > 0}} -->
  <div style="background:#fff8e1;border:1px solid #ff9800;padding:12px 16px;margin-top:8px;border-radius:4px">
    <strong>🟡 MRP Planning Warning</strong>
    <p style="margin:6px 0">These materials have a plant view but MRP type = <strong>ND</strong> (no planning). MRP will NOT raise planned orders or purchase reqs for them:</p>
    <ul>
      <!-- {{#each mrp_warn_materials}} -->
      <li><code>{{material_id}}</code> — {{description}} → update MRP type to <strong>PD</strong> + assign MRP controller</li>
      <!-- {{/each}} -->
    </ul>
  </div>
  <!-- {{/if}} -->

  <!-- FOOTER -->
  <div style="background:#f0f4f8;padding:8px 16px;font-size:11px;color:#666;border-radius:0 0 6px 6px;border-top:1px solid #ccc">
    Verified: {{timestamp}} | Source: get_material(full=true) per material | Plant: {{plant}}
  </div>

</div>
```

## Chip helpers
- plant_view_chip: `<span style="background:#d4edda;color:#155724;padding:2px 8px;border-radius:10px">✅ Extended</span>` if true, else `<span style="background:#f8d7da;color:#721c24;padding:2px 8px;border-radius:10px">❌ Missing</span>`
- mrp_type_chip: green `PD` chip, orange `ND` chip, red `—` if blank
- verdict_colour: `#28a745` (green) for PASS, `#dc3545` (red) for FAIL
- missing_colour: `#dc3545` if missing > 0, else `#28a745`
- row_colour: alternating `#ffffff` / `#f8f9fa`
- status_colour: `#28a745` CONFIRMED, `#dc3545` MISSING, `#fd7e14` MRP_WARN

