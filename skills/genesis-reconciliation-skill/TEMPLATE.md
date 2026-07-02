# TEMPLATE — Genesis Reconciliation Card

Use this HTML template. Replace ALL `{{placeholders}}` with live values.

```html
<div style="font-family:Arial,sans-serif;max-width:680px;border:1px solid #d0d0d0;border-radius:8px;overflow:hidden">

  <!-- HEADER -->
  <div style="background:#1a3c5e;color:white;padding:12px 16px;display:flex;justify-content:space-between;align-items:center">
    <div>
      <span style="font-size:17px;font-weight:bold">Genesis Reconciliation Report</span>
      <span style="margin-left:10px;font-size:12px;opacity:0.75">{{DATE}}</span>
    </div>
    <div style="font-size:12px;opacity:0.85">Plant {{PLANT}}</div>
  </div>

  <!-- ASSEMBLY BANNER -->
  <div style="background:#f4f7fb;padding:8px 16px;border-bottom:1px solid #d0d0d0;display:grid;grid-template-columns:repeat(3,1fr);gap:8px">
    <div><div style="font-size:10px;color:#666">ASSEMBLY</div><div style="font-weight:bold">{{PARENT_MATNR}}</div></div>
    <div><div style="font-size:10px;color:#666">DESCRIPTION</div><div style="font-weight:bold">{{PARENT_DESC}}</div></div>
    <div><div style="font-size:10px;color:#666">TYPE</div><div>{{PARENT_TYPE}} · {{COMPONENT_COUNT}} components</div></div>
  </div>

  <!-- SCORECARD TABLE -->
  <table style="width:100%;border-collapse:collapse;font-size:13px">
    <thead>
      <tr style="background:#e8edf3;color:#333">
        <th style="padding:8px 12px;text-align:left">Object Type</th>
        <th style="padding:8px 12px;text-align:center">Planned</th>
        <th style="padding:8px 12px;text-align:center">Created</th>
        <th style="padding:8px 12px;text-align:center">Result</th>
      </tr>
    </thead>
    <tbody>
      <tr style="border-bottom:1px solid #eee">
        <td style="padding:7px 12px">Material Masters</td>
        <td style="padding:7px 12px;text-align:center">{{PLANNED_MATERIALS}}</td>
        <td style="padding:7px 12px;text-align:center">{{CREATED_MATERIALS}}</td>
        <td style="padding:7px 12px;text-align:center">{{RESULT_MATERIALS}}</td>
      </tr>
      <tr style="border-bottom:1px solid #eee;background:#fafafa">
        <td style="padding:7px 12px">PIRs</td>
        <td style="padding:7px 12px;text-align:center">{{PLANNED_PIRS}}</td>
        <td style="padding:7px 12px;text-align:center">{{CREATED_PIRS}}</td>
        <td style="padding:7px 12px;text-align:center">{{RESULT_PIRS}}</td>
      </tr>
      <tr style="border-bottom:1px solid #eee">
        <td style="padding:7px 12px">Standard Cost Records</td>
        <td style="padding:7px 12px;text-align:center">{{PLANNED_COSTS}}</td>
        <td style="padding:7px 12px;text-align:center">{{CREATED_COSTS}}</td>
        <td style="padding:7px 12px;text-align:center">{{RESULT_COSTS}}</td>
      </tr>
      <tr style="border-bottom:1px solid #eee;background:#fafafa">
        <td style="padding:7px 12px">BOM</td>
        <td style="padding:7px 12px;text-align:center">{{PLANNED_BOMS}}</td>
        <td style="padding:7px 12px;text-align:center">{{CREATED_BOMS}}</td>
        <td style="padding:7px 12px;text-align:center">{{RESULT_BOMS}}</td>
      </tr>
      <tr style="border-bottom:1px solid #eee">
        <td style="padding:7px 12px">Routing</td>
        <td style="padding:7px 12px;text-align:center">{{PLANNED_ROUTINGS}}</td>
        <td style="padding:7px 12px;text-align:center">{{CREATED_ROUTINGS}}</td>
        <td style="padding:7px 12px;text-align:center">{{RESULT_ROUTINGS}}</td>
      </tr>
      <tr style="border-bottom:1px solid #eee;background:#fafafa">
        <td style="padding:7px 12px">Production Version</td>
        <td style="padding:7px 12px;text-align:center">{{PLANNED_PRODVERS}}</td>
        <td style="padding:7px 12px;text-align:center">{{CREATED_PRODVERS}}</td>
        <td style="padding:7px 12px;text-align:center">{{RESULT_PRODVERS}}</td>
      </tr>
      <tr style="border-bottom:1px solid #eee">
        <td style="padding:7px 12px">Sales Order (Demand)</td>
        <td style="padding:7px 12px;text-align:center">{{PLANNED_SO}}</td>
        <td style="padding:7px 12px;text-align:center">{{CREATED_SO}}</td>
        <td style="padding:7px 12px;text-align:center">{{RESULT_SO}}</td>
      </tr>
      <tr style="border-bottom:2px solid #ccc;background:#fafafa">
        <td style="padding:7px 12px">MRP Run</td>
        <td style="padding:7px 12px;text-align:center">{{PLANNED_MRP}}</td>
        <td style="padding:7px 12px;text-align:center">{{CREATED_MRP}}</td>
        <td style="padding:7px 12px;text-align:center">{{RESULT_MRP}}</td>
      </tr>
      <!-- TOTAL ROW -->
      <tr style="background:#1a3c5e;color:white;font-weight:bold">
        <td style="padding:9px 12px">TOTAL</td>
        <td style="padding:9px 12px;text-align:center">{{TOTAL_PLANNED}}</td>
        <td style="padding:9px 12px;text-align:center">{{TOTAL_CREATED}}</td>
        <td style="padding:9px 12px;text-align:center;font-size:15px">{{TOTAL_RESULT}}</td>
      </tr>
    </tbody>
  </table>

  <!-- FOOTER -->
  <div style="background:#f4f7fb;padding:7px 16px;font-size:11px;color:#555;border-top:1px solid #ddd">
    ✅ = all objects created &nbsp;|&nbsp; ❌ = gap (escalate) &nbsp;|&nbsp; ⚠️ = unexpected extra objects
    &nbsp;&nbsp;·&nbsp;&nbsp; SAP S/4HANA · Plant {{PLANT}} · {{DATE}}
  </div>

</div>
```
