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
