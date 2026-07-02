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
