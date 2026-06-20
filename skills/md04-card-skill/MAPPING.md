# MD04 Card — Field Mapping (Screen → Card)

How to map raw MD04 screen data to the rendered card template.

## Header Mapping
```
screen "Material:"        → header.material
screen "Description:"     → header.description
screen "Plant:"           → header.plant
screen "MRP Area:"        → header.mrp_area
screen text beside area   → header.plant_name
screen "MRP type:"        → header.mrp_type
screen "Material Type:"   → header.material_type
screen "Unit:"            → header.base_unit
title bar timestamp       → header.as_of
```

## Line Item Mapping
Each row in the MRP elements grid maps to one `line` object:
```
col "Date"            → line.date
col "MRP el."         → line.mrp_element
col "MRP element data"→ line.element_data
col "Receipt/Reqmt"   → line.receipt_reqmt  (strip trailing "-" → negative number)
col "Available Qty"   → line.available_qty
col "Pro…"            → line.prod_version
```

## MRP Element → Icon/Badge
| mrp_element | Badge colour | Symbol |
|-------------|-------------|--------|
| Stock       | grey        | 📦 |
| PldOrd      | blue        | 🏭 |
| CusOrd      | red         | 🛒 |
| PurRqs      | orange      | 📋 |
| PurOrd      | green       | 🟢 |
| PrdOrd      | blue        | ⚙️ |
| IndReq      | purple      | 📈 |

## Available Qty → Colour
| Condition | Colour |
|-----------|--------|
| qty > 0   | green  |
| qty = 0   | amber  |
| qty < 0   | red    |

## BOM Tree Mapping
Left-panel nodes → `bom_tree` list of `{parent, children[]}` objects.
