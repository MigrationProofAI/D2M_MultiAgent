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
