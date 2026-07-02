# BOM Display Card — Field Mapping (Screen → Card)

How to map raw SAP BOM data (from get_bom + get_material) to the rendered card template.

## Header Mapping
```
screen "Material:"        → header.material
screen text beside mat.   → header.description
screen "Plant:"           → header.plant
screen text beside plant  → header.plant_name
screen "Alternative BOM:" → header.alternative_bom
BOM doc number (API)      → header.bom_number
```

## Line Item Mapping
Each BOM component row maps to one `line` object:
```
col "Item"                 → line.item
col "ICt"                  → line.item_category
col "Component"            → line.component
col "Component description"→ line.component_description
col "Quantity"             → line.quantity
material type (resolved)   → line.material_type
```

## Item Category → Badge
| ICt | Label | Badge colour |
|-----|-------|--------------|
| L   | Stock | #1a6bbf (blue) |
| N   | Non-Stock | #e67e22 (orange) |
| D   | Document  | #8e44ad (purple) |
| T   | Text      | #888888 (grey) |

## Material Type → Badge
| Type | Label | Badge colour |
|------|-------|--------------|
| FERT | Finished | #155724 bg #d4edda |
| HALB | Semi-Fin | #1a6bbf bg #d0e8ff |
| HAWA | Trading  | #e67e22 bg #fff3cd |
| ROH  | Raw Mat  | #888888 bg #f0f0f0 |

## Quantity Colour
| Condition | colour |
|-----------|--------|
| qty = 1   | #333 |
| qty > 1   | #1a6bbf (bold) |
