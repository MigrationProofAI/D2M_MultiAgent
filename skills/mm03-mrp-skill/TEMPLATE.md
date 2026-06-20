# MM03 Full MRP Skill — HTML Card Template

Render this template populated with live data tokens.

```html
<div style="font-family:Segoe UI,Arial,sans-serif;max-width:960px;margin:0 auto;font-size:13px;color:#1a1a1a;">

  <!-- HEADER -->
  <div style="background:linear-gradient(135deg,#1a3c5e 0%,#1a6bbf 100%);color:#fff;padding:16px 24px;border-radius:8px 8px 0 0;display:flex;justify-content:space-between;align-items:center;">
    <div>
      <div style="font-size:19px;font-weight:700;">{{description}}</div>
      <div style="font-size:12px;opacity:0.8;margin-top:3px;">Material {{material}} &nbsp;·&nbsp; Plant {{plant}} &nbsp;·&nbsp; Base UoM: {{baseUnit}}</div>
    </div>
    <div style="text-align:right;font-size:12px;opacity:0.75;"><div>SAP S/4HANA</div><div>Material Master</div></div>
  </div>

  <!-- TAB BAR -->
  <div style="display:flex;background:#e8edf2;border-bottom:2px solid #1a6bbf;">
    <div style="padding:9px 18px;font-weight:700;color:#fff;background:#1a6bbf;font-size:12px;">Basic Data 1</div>
    <div style="padding:9px 18px;font-weight:600;color:#1a3c5e;font-size:12px;border-right:1px solid #ccd3db;">MRP 1</div>
    <div style="padding:9px 18px;font-weight:600;color:#1a3c5e;font-size:12px;border-right:1px solid #ccd3db;">MRP 2</div>
    <div style="padding:9px 18px;font-weight:600;color:#1a3c5e;font-size:12px;border-right:1px solid #ccd3db;">MRP 3</div>
    <div style="padding:9px 18px;font-weight:600;color:#1a3c5e;font-size:12px;">Production Version</div>
  </div>

  <!-- BASIC DATA 1 -->
  <!-- MRP 1 -->
  <!-- MRP 2 -->
  <!-- MRP 3 -->
  <!-- PRODUCTION VERSION -->

  <!-- FOOTER -->
  <div style="background:#e8edf2;border:1px solid #d0d7de;border-top:none;border-radius:0 0 8px 8px;padding:8px 24px;display:flex;justify-content:space-between;font-size:11px;color:#888;">
    <div>5 views · Basic Data 1 · MRP 1 · MRP 2 · MRP 3 · Production Version</div>
    <div>SAP S/4HANA · mm03-mrp-skill · Material {{material}}</div>
  </div>

</div>
```
