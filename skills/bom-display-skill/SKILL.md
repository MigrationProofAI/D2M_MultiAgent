---
name: bom-display-skill
description: Render a SAP CS03 BOM Display card with component table, HALB sub-assembly expansion, material type chips, and colour-coded quantities
when_to_trigger: show BOM, display BOM, CS03, BOM for material, list components, what's in the BOM
---

# bom-display-skill

Render a card from LIVE SAP data into the STRUCTURED-DATA panel (not just chat). The runtime does
NOT execute inline scripts, so YOU bind the data and the rendering goes through render_card.

## Invoke recipe
1. Call the sources named in MAPPING (run_mrp / get_material / get_bom) for the material + plant in play.
2. Bind the returned data into the SCHEMA shape using the MAPPING rules.
3. Build the card as HTML following the TEMPLATE layout (sections, colours, chips).
4. Call render_card(title=..., content=<the card HTML>). It surfaces in the Structured Data panel.

## MAPPING.md

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


## SCHEMA.md

# BOM Display Card — Data Schema

Fields extracted from SAP CS03 / MM03 BOM Display screen ("Display material BOM: General Item Overview").

## Header Fields
| Field | SAP Label | Notes |
|-------|-----------|-------|
| material | Material | Material number, e.g. 11813 |
| description | (next to material field) | Material short text, e.g. "Skateboard Complete Assembly" |
| plant | Plant | Plant code, e.g. 1710 |
| plant_name | (next to plant code) | e.g. "Plant 1 US" |
| alternative_bom | Alternative BOM | Usually 1 |
| bom_number | BOM Number | Internal BOM doc number, e.g. 00000524 |
| valid_from | Valid From | Validity start date |
| valid_to | Valid To | Validity end date |

## Line Item Fields (BOM Components)
| Field | SAP Column | Notes |
|-------|-----------|-------|
| item | Item | Item number, e.g. 0010, 0020 |
| item_category | ICt | L = stock item, N = non-stock, D = document, T = text |
| component | Component | Component material number |
| component_description | Component description | Short text of the component |
| quantity | Quantity | BOM quantity |
| unit | Unit | Base unit of measure |
| material_type | (resolved) | FERT / HALB / HAWA / ROH |


## TEMPLATE.md

# BOM Display Card — Render Template

Use this HTML template. Replace `{{placeholders}}` with live data.

```html
<div style="font-family:Arial,sans-serif;max-width:820px;border:1px solid #d0d0d0;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08)">

  <!-- HEADER BAND -->
  <div style="background:#1a3c5e;color:white;padding:12px 16px;display:flex;justify-content:space-between;align-items:center">
    <div>
      <span style="font-size:17px;font-weight:bold">CS03 — Display Material BOM</span>
      <span style="margin-left:10px;font-size:11px;opacity:0.75">General Item Overview</span>
    </div>
    <div style="font-size:12px;opacity:0.85">Plant {{plant}} · {{plant_name}}</div>
  </div>

  <!-- MATERIAL HEADER -->
  <div style="background:#f4f7fb;padding:10px 16px;display:grid;grid-template-columns:repeat(4,1fr);gap:8px;border-bottom:2px solid #1a3c5e">
    <div>
      <div style="font-size:10px;color:#666;text-transform:uppercase">Material</div>
      <div style="font-weight:bold;font-size:16px;color:#1a3c5e">{{material}}</div>
    </div>
    <div style="grid-column:span 2">
      <div style="font-size:10px;color:#666;text-transform:uppercase">Description</div>
      <div style="font-weight:bold;font-size:14px">{{description}}</div>
    </div>
    <div>
      <div style="font-size:10px;color:#666;text-transform:uppercase">Alt. BOM / BOM#</div>
      <div style="font-size:13px">{{alternative_bom}} &nbsp;·&nbsp; <span style="color:#555">{{bom_number}}</span></div>
    </div>
  </div>

  <!-- TAB BAR (static, Material tab active) -->
  <div style="background:#fff;border-bottom:1px solid #d0d0d0;padding:0 16px;display:flex;gap:24px">
    <div style="padding:8px 0;font-size:13px;font-weight:bold;color:#1a6bbf;border-bottom:2px solid #1a6bbf">Material</div>
    <div style="padding:8px 0;font-size:13px;color:#888">Document</div>
    <div style="padding:8px 0;font-size:13px;color:#888">General</div>
  </div>

  <!-- BOM LINES TABLE -->
  <table style="width:100%;border-collapse:collapse;font-size:13px">
    <thead>
      <tr style="background:#e8edf3;color:#333">
        <th style="padding:7px 10px;text-align:center;width:32px"></th>
        <th style="padding:7px 10px;text-align:left;width:60px">Item</th>
        <th style="padding:7px 10px;text-align:center;width:40px">ICt</th>
        <th style="padding:7px 10px;text-align:left">Component</th>
        <th style="padding:7px 10px;text-align:left">Component Description</th>
        <th style="padding:7px 10px;text-align:left;width:80px">Type</th>
        <th style="padding:7px 10px;text-align:right;width:80px">Quantity</th>
      </tr>
    </thead>
    <tbody>
      <!-- Repeat for each BOM line: -->
      <tr style="border-bottom:1px solid #eee">
        <td style="padding:6px 10px;text-align:center"><input type="checkbox" disabled></td>
        <td style="padding:6px 10px;color:#555">{{line.item}}</td>
        <td style="padding:6px 10px;text-align:center">
          <span style="background:#1a6bbf;color:white;border-radius:4px;padding:2px 6px;font-size:11px">{{line.item_category}}</span>
        </td>
        <td style="padding:6px 10px">
          <span style="color:#1a6bbf;font-weight:bold;text-decoration:underline;cursor:pointer">{{line.component}}</span>
        </td>
        <td style="padding:6px 10px;color:#333">{{line.component_description}}</td>
        <td style="padding:6px 10px">
          <span style="background:{{line.type_bg}};color:{{line.type_color}};border-radius:4px;padding:2px 6px;font-size:11px">{{line.material_type}}</span>
        </td>
        <td style="padding:6px 10px;text-align:right;font-weight:bold;color:{{line.qty_color}}">{{line.quantity}}</td>
      </tr>
      <!-- /repeat -->
    </tbody>
  </table>

  <!-- SUMMARY FOOTER -->
  <div style="background:#f4f7fb;padding:8px 16px;border-top:1px solid #d0d0d0;display:flex;justify-content:space-between;font-size:12px;color:#555">
    <span>{{component_count}} component(s) &nbsp;·&nbsp; Total items: {{total_qty}}</span>
    <span>SAP S/4HANA · CS03 · Plant {{plant}} · {{material}}</span>
  </div>

</div>
```

## Badge Colour Values
| Material Type | type_bg | type_color |
|---|---|---|
| FERT | #d4edda | #155724 |
| HALB | #d0e8ff | #1a6bbf |
| HAWA | #fff3cd | #856404 |
| ROH  | #f0f0f0 | #555555 |

## Quantity Colour
| qty > 1 | #1a6bbf |
| qty = 1 | #333333 |

