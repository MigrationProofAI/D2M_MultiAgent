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
