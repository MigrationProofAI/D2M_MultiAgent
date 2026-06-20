---
name: md04-card-skill
description: Render a SAP MD04 Stock/Requirements List as a structured HTML card with colour-coded MRP elements, traffic-light available qty, and BOM tree summary
when_to_trigger: show MD04, MD04 card, stock requirements list, after run_mrp, render MD04
---

# md04-card-skill

Render a card from LIVE SAP data into the STRUCTURED-DATA panel (not just chat). The runtime does
NOT execute inline scripts, so YOU bind the data and the rendering goes through render_card.

## Invoke recipe
1. Call the sources named in MAPPING (run_mrp / get_material / get_bom) for the material + plant in play.
2. Bind the returned data into the SCHEMA shape using the MAPPING rules.
3. Build the card as HTML following the TEMPLATE layout (sections, colours, chips).
4. Call render_card(title=..., content=<the card HTML>). It surfaces in the Structured Data panel.

## MAPPING.md

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


## SCHEMA.md

# MD04 Card — Data Schema

Fields extracted from the SAP MD04 Stock/Requirements List screen (transaction MD04).

## Header Fields
| Field | SAP Label | Notes |
|-------|-----------|-------|
| material | Material | Material number |
| description | Description | Material short text |
| plant | Plant | Plant code |
| mrp_area | MRP Area | Usually = plant |
| plant_name | (next to MRP Area) | e.g. "Plant 1 US" |
| mrp_type | MRP type | PD, ND, VB, etc. |
| material_type | Material Type | FERT, HALB, HAWA, ROH… |
| base_unit | Unit | EA, KG, PC… |
| as_of | Title timestamp | "as of HH:MM hrs" |

## Line Items (MRP Elements table)
| Field | SAP Column | Notes |
|-------|-----------|-------|
| date | Date | DD.MM.YYYY |
| mrp_element | MRP el. | Stock, PldOrd, CusOrd, PurRqs, PurOrd, PrdOrd, etc. |
| element_data | MRP element data | Document number / reference |
| rescheduling | Reschedulin… | Rescheduling date if any |
| exception | E… | Exception message code |
| receipt_reqmt | Receipt/Reqmt | Positive = receipt, Negative = requirement |
| available_qty | Available Qty | Running cumulative available stock |
| prod_version | Pro… | Production version (e.g. 0001) |

## BOM Tree (left panel)
| Field | Notes |
|-------|-------|
| tree_nodes | List of material numbers shown in the pegged requirements tree |
| tree_structure | Parent → child groupings visible in the left panel |


## TEMPLATE.md

# MD04 Card — Render Template

Use this HTML template. Replace `{{placeholders}}` with live data.

```html
<div style="font-family:Arial,sans-serif;max-width:780px;border:1px solid #d0d0d0;border-radius:8px;overflow:hidden">

  <!-- HEADER BAND -->
  <div style="background:#1a3c5e;color:white;padding:12px 16px;display:flex;justify-content:space-between;align-items:center">
    <div>
      <span style="font-size:18px;font-weight:bold">MD04 — Stock/Requirements List</span>
      <span style="margin-left:12px;font-size:12px;opacity:0.75">as of {{as_of}}</span>
    </div>
    <div style="font-size:12px;opacity:0.85">Plant {{plant}} · {{plant_name}}</div>
  </div>

  <!-- MATERIAL HEADER -->
  <div style="background:#f4f7fb;padding:10px 16px;display:grid;grid-template-columns:repeat(4,1fr);gap:8px;border-bottom:1px solid #d0d0d0">
    <div><div style="font-size:10px;color:#666">MATERIAL</div><div style="font-weight:bold;font-size:15px">{{material}}</div></div>
    <div><div style="font-size:10px;color:#666">DESCRIPTION</div><div style="font-weight:bold">{{description}}</div></div>
    <div><div style="font-size:10px;color:#666">TYPE / MRP</div><div>{{material_type}} · {{mrp_type}}</div></div>
    <div><div style="font-size:10px;color:#666">UNIT</div><div>{{base_unit}}</div></div>
  </div>

  <!-- MRP LINES TABLE -->
  <table style="width:100%;border-collapse:collapse;font-size:13px">
    <thead>
      <tr style="background:#e8edf3;color:#333">
        <th style="padding:7px 10px;text-align:left">Date</th>
        <th style="padding:7px 10px;text-align:left">MRP Element</th>
        <th style="padding:7px 10px;text-align:left">Element Data</th>
        <th style="padding:7px 10px;text-align:right">Receipt/Reqmt</th>
        <th style="padding:7px 10px;text-align:right">Available Qty</th>
        <th style="padding:7px 10px;text-align:center">Prod.Ver.</th>
      </tr>
    </thead>
    <tbody>
      <!-- Repeat for each line item: -->
      <!-- STOCK row example -->
      <tr style="border-bottom:1px solid #eee">
        <td style="padding:6px 10px">{{line.date}}</td>
        <td style="padding:6px 10px">
          <span style="background:{{line.badge_color}};color:white;border-radius:4px;padding:2px 7px;font-size:11px">{{line.mrp_element}}</span>
        </td>
        <td style="padding:6px 10px;color:#555">{{line.element_data}}</td>
        <td style="padding:6px 10px;text-align:right;color:{{line.reqmt_color}}">{{line.receipt_reqmt}}</td>
        <td style="padding:6px 10px;text-align:right;font-weight:bold;color:{{line.avail_color}}">{{line.available_qty}}</td>
        <td style="padding:6px 10px;text-align:center;color:#888">{{line.prod_version}}</td>
      </tr>
      <!-- /repeat -->
    </tbody>
  </table>

  <!-- BOM TREE SUMMARY (optional) -->
  <div style="background:#f9f9f9;padding:10px 16px;border-top:1px solid #e0e0e0;font-size:12px;color:#555">
    <strong>BOM Explosion:</strong> {{bom_tree_summary}}
  </div>

  <!-- FOOTER -->
  <div style="background:#1a3c5e;color:white;padding:6px 16px;font-size:11px;text-align:right">
    SAP S/4HANA · MD04 · {{plant}} · {{material}}
  </div>

</div>
```

## Badge Colour Values (inline CSS)
| MRP Element | badge_color |
|-------------|-------------|
| Stock  | #888888 |
| PldOrd | #1a6bbf |
| CusOrd | #c0392b |
| PurRqs | #e67e22 |
| PurOrd | #27ae60 |
| PrdOrd | #2980b9 |
| IndReq | #8e44ad |

## Available Qty Colour Values
| Condition | avail_color |
|-----------|-------------|
| > 0 | #27ae60 |
| = 0 | #e67e22 |
| < 0 | #c0392b |

## Receipt/Reqmt Colour Values
| Condition | reqmt_color |
|-----------|-------------|
| positive  | #27ae60 |
| negative  | #c0392b |
| zero/blank| #333333 |
```

