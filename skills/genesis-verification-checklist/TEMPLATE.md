# Genesis Verification Checklist — Render Template

```html
<div style="font-family:Arial,sans-serif;max-width:900px;border:1px solid #d0d0d0;border-radius:8px;overflow:hidden">

  <!-- HEADER -->
  <div style="background:#1a3c5e;color:white;padding:12px 16px;display:flex;justify-content:space-between;align-items:center">
    <span style="font-size:17px;font-weight:bold">🔍 Genesis Verification Checklist</span>
    <span style="font-size:12px;opacity:.8">Plant {{plant}} · {{timestamp}}</span>
  </div>

  <!-- ASSEMBLY IDENTITY -->
  <div style="background:#f4f7fb;padding:10px 16px;display:grid;grid-template-columns:repeat(3,1fr);gap:8px;border-bottom:1px solid #d0d0d0">
    <div><div style="font-size:10px;color:#666">FINISHED GOOD</div><div style="font-weight:bold">{{fert_number}} — {{fert_description}}</div></div>
    <div><div style="font-size:10px;color:#666">SUB-ASSEMBLIES (HALB)</div><div style="font-weight:bold">{{halb_count}}</div></div>
    <div><div style="font-size:10px;color:#666">BOUGHT COMPONENTS (HAWA)</div><div style="font-weight:bold">{{hawa_count}}</div></div>
  </div>

  <!-- CHECK LEGEND -->
  <div style="padding:6px 16px;background:#fffde7;border-bottom:1px solid #ffe082;font-size:11px;color:#7b5800">
    ✅ PASS — confirmed at SAP key &nbsp;|&nbsp; ❌ FAIL — readable but absent/wrong (fixable gap) &nbsp;|&nbsp; ⚠️ WARN — exists with anomaly &nbsp;|&nbsp; — N/A not applicable
  </div>

  <!-- CHECK 1: MATERIAL EXISTENCE -->
  <div style="padding:8px 16px 2px;font-size:11px;font-weight:bold;color:#1a3c5e;background:#eef2f8;text-transform:uppercase;letter-spacing:.5px">
    Check 1 — Material Existence &nbsp;<span style="font-weight:normal;color:#555">get_material(material_id) · all materials</span>
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:12px">
    <thead><tr style="background:#e8edf3;color:#333">
      <th style="padding:6px 10px;text-align:left">Material #</th>
      <th style="padding:6px 10px;text-align:left">Description</th>
      <th style="padding:6px 10px;text-align:left">Type</th>
      <th style="padding:6px 10px;text-align:left">Plant View</th>
      <th style="padding:6px 10px;text-align:center">Status</th>
    </tr></thead>
    <tbody>
      <!-- repeat for each material -->
      <tr style="border-bottom:1px solid #eee">
        <td style="padding:5px 10px;font-weight:bold">{{mat.number}}</td>
        <td style="padding:5px 10px;color:#555">{{mat.description}}</td>
        <td style="padding:5px 10px"><span style="background:{{mat.type_color}};color:white;border-radius:3px;padding:1px 6px;font-size:10px">{{mat.type}}</span></td>
        <td style="padding:5px 10px;color:#777">{{mat.plant}}</td>
        <td style="padding:5px 10px;text-align:center;font-size:15px">{{mat.status}}</td>
      </tr>
      <!-- /repeat -->
    </tbody>
  </table>

  <!-- CHECK 2: BOM COMPLETENESS -->
  <div style="padding:8px 16px 2px;font-size:11px;font-weight:bold;color:#1a3c5e;background:#eef2f8;text-transform:uppercase;letter-spacing:.5px">
    Check 2 — BOM Completeness &nbsp;<span style="font-weight:normal;color:#555">get_bom(material, plant) · FERT + all HALBs</span>
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:12px">
    <thead><tr style="background:#e8edf3;color:#333">
      <th style="padding:6px 10px;text-align:left">Parent Material</th>
      <th style="padding:6px 10px;text-align:left">BOM Number</th>
      <th style="padding:6px 10px;text-align:left">Usage / Alt</th>
      <th style="padding:6px 10px;text-align:right">Item Count</th>
      <th style="padding:6px 10px;text-align:center">Status</th>
    </tr></thead>
    <tbody>
      <tr style="border-bottom:1px solid #eee">
        <td style="padding:5px 10px;font-weight:bold">{{bom.parent}} — {{bom.description}}</td>
        <td style="padding:5px 10px;color:#555">{{bom.number}}</td>
        <td style="padding:5px 10px;color:#777">{{bom.usage}} / {{bom.alt}}</td>
        <td style="padding:5px 10px;text-align:right">{{bom.items}}</td>
        <td style="padding:5px 10px;text-align:center;font-size:15px">{{bom.status}}</td>
      </tr>
    </tbody>
  </table>

  <!-- CHECK 3: ROUTING -->
  <div style="padding:8px 16px 2px;font-size:11px;font-weight:bold;color:#1a3c5e;background:#eef2f8;text-transform:uppercase;letter-spacing:.5px">
    Check 3 — Routing &nbsp;<span style="font-weight:normal;color:#555">read_routing(material, plant) · FERT + all HALBs</span>
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:12px">
    <thead><tr style="background:#e8edf3;color:#333">
      <th style="padding:6px 10px;text-align:left">Material</th>
      <th style="padding:6px 10px;text-align:left">Routing Group (PLNNR)</th>
      <th style="padding:6px 10px;text-align:left">Counter (PLNAL)</th>
      <th style="padding:6px 10px;text-align:left">Type (PLNTY)</th>
      <th style="padding:6px 10px;text-align:center">Status</th>
    </tr></thead>
    <tbody>
      <tr style="border-bottom:1px solid #eee">
        <td style="padding:5px 10px;font-weight:bold">{{rte.material}} — {{rte.description}}</td>
        <td style="padding:5px 10px;color:#555">{{rte.group}}</td>
        <td style="padding:5px 10px;color:#777">{{rte.counter}}</td>
        <td style="padding:5px 10px;color:#777">{{rte.type}}</td>
        <td style="padding:5px 10px;text-align:center;font-size:15px">{{rte.status}}</td>
      </tr>
    </tbody>
  </table>

  <!-- CHECK 4: PRODUCTION VERSION -->
  <div style="padding:8px 16px 2px;font-size:11px;font-weight:bold;color:#1a3c5e;background:#eef2f8;text-transform:uppercase;letter-spacing:.5px">
    Check 4 — Production Version &nbsp;<span style="font-weight:normal;color:#555">read_production_version(material, plant) · FERT + all HALBs</span>
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:12px">
    <thead><tr style="background:#e8edf3;color:#333">
      <th style="padding:6px 10px;text-align:left">Material</th>
      <th style="padding:6px 10px;text-align:left">Version (VERID)</th>
      <th style="padding:6px 10px;text-align:left">BOM Usage / Alt</th>
      <th style="padding:6px 10px;text-align:left">Lot Size</th>
      <th style="padding:6px 10px;text-align:center">Status</th>
    </tr></thead>
    <tbody>
      <tr style="border-bottom:1px solid #eee">
        <td style="padding:5px 10px;font-weight:bold">{{pv.material}} — {{pv.description}}</td>
        <td style="padding:5px 10px;color:#555">{{pv.verid}}</td>
        <td style="padding:5px 10px;color:#777">{{pv.usage}} / {{pv.alt}}</td>
        <td style="padding:5px 10px;color:#777">{{pv.lot_from}}–{{pv.lot_to}}</td>
        <td style="padding:5px 10px;text-align:center;font-size:15px">{{pv.status}}</td>
      </tr>
    </tbody>
  </table>

  <!-- CHECK 5: PIR -->
  <div style="padding:8px 16px 2px;font-size:11px;font-weight:bold;color:#1a3c5e;background:#eef2f8;text-transform:uppercase;letter-spacing:.5px">
    Check 5 — Purchase Info Record &nbsp;<span style="font-weight:normal;color:#555">read_pir(material) · all HAWAs</span>
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:12px">
    <thead><tr style="background:#e8edf3;color:#333">
      <th style="padding:6px 10px;text-align:left">Material</th>
      <th style="padding:6px 10px;text-align:left">PIR Number</th>
      <th style="padding:6px 10px;text-align:left">Supplier</th>
      <th style="padding:6px 10px;text-align:right">Net Price</th>
      <th style="padding:6px 10px;text-align:center">Status</th>
    </tr></thead>
    <tbody>
      <tr style="border-bottom:1px solid #eee">
        <td style="padding:5px 10px;font-weight:bold">{{pir.material}} — {{pir.description}}</td>
        <td style="padding:5px 10px;color:#555">{{pir.number}}</td>
        <td style="padding:5px 10px;color:#777">{{pir.supplier}}</td>
        <td style="padding:5px 10px;text-align:right">{{pir.currency}} {{pir.price}}</td>
        <td style="padding:5px 10px;text-align:center;font-size:15px">{{pir.status}}</td>
      </tr>
    </tbody>
  </table>

  <!-- CHECK 6: COST CONDITION -->
  <div style="padding:8px 16px 2px;font-size:11px;font-weight:bold;color:#1a3c5e;background:#eef2f8;text-transform:uppercase;letter-spacing:.5px">
    Check 6 — Cost Condition (PPR0) &nbsp;<span style="font-weight:normal;color:#555">read_cost_condition(material) · all HAWAs</span>
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:12px">
    <thead><tr style="background:#e8edf3;color:#333">
      <th style="padding:6px 10px;text-align:left">Material</th>
      <th style="padding:6px 10px;text-align:left">Condition Record</th>
      <th style="padding:6px 10px;text-align:right">Rate</th>
      <th style="padding:6px 10px;text-align:left">Validity</th>
      <th style="padding:6px 10px;text-align:center">Status</th>
    </tr></thead>
    <tbody>
      <tr style="border-bottom:1px solid #eee">
        <td style="padding:5px 10px;font-weight:bold">{{cc.material}} — {{cc.description}}</td>
        <td style="padding:5px 10px;color:#555">{{cc.record}}</td>
        <td style="padding:5px 10px;text-align:right">{{cc.currency}} {{cc.rate}}</td>
        <td style="padding:5px 10px;color:#777">{{cc.valid_from}} – {{cc.valid_to}}</td>
        <td style="padding:5px 10px;text-align:center;font-size:15px">{{cc.status}}</td>
      </tr>
    </tbody>
  </table>

  <!-- CHECK 7: MRP PLANABILITY -->
  <div style="padding:8px 16px 2px;font-size:11px;font-weight:bold;color:#c0392b;background:#fdf3f3;text-transform:uppercase;letter-spacing:.5px;border-top:2px solid #e74c3c">
    Check 7 — MRP Planability ⚠️ &nbsp;<span style="font-weight:normal;color:#555">get_material(full=true) · ALL materials · SILENT-FAIL RISK</span>
  </div>
  <div style="padding:4px 16px 6px;background:#fdf3f3;font-size:11px;color:#7b1414;border-bottom:1px solid #f5c6c6">
    ⚠️ <strong>extend_to_plant defaults to MRPType=ND (no planning).</strong> A material with ND is invisible to MRP — no planned orders, no purchase reqs, even with a BOM and routing. Check every material.
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:12px">
    <thead><tr style="background:#fce8e8;color:#333">
      <th style="padding:6px 10px;text-align:left">Material</th>
      <th style="padding:6px 10px;text-align:left">Type</th>
      <th style="padding:6px 10px;text-align:center">MRP Type</th>
      <th style="padding:6px 10px;text-align:center">MRP Controller</th>
      <th style="padding:6px 10px;text-align:center">Proc Type</th>
      <th style="padding:6px 10px;text-align:center">Status</th>
    </tr></thead>
    <tbody>
      <!-- repeat for ALL materials -->
      <tr style="border-bottom:1px solid #eee">
        <td style="padding:5px 10px;font-weight:bold">{{mrp.material}} — {{mrp.description}}</td>
        <td style="padding:5px 10px"><span style="background:{{mrp.type_color}};color:white;border-radius:3px;padding:1px 6px;font-size:10px">{{mrp.mat_type}}</span></td>
        <td style="padding:5px 10px;text-align:center">
          <span style="background:{{mrp.mrptype_color}};color:white;border-radius:3px;padding:2px 8px;font-size:11px;font-weight:bold">{{mrp.mrp_type}}</span>
        </td>
        <td style="padding:5px 10px;text-align:center;color:#555">{{mrp.mrp_controller}}</td>
        <td style="padding:5px 10px;text-align:center">
          <span style="background:{{mrp.proctype_color}};color:white;border-radius:3px;padding:2px 8px;font-size:11px">{{mrp.proc_type}}</span>
        </td>
        <td style="padding:5px 10px;text-align:center;font-size:15px">{{mrp.status}}</td>
      </tr>
      <!-- /repeat -->
    </tbody>
  </table>
  <!-- MRP Type colour rules: PD=#27ae60, ND=#c0392b, blank=#888 -->
  <!-- Proc Type colour rules: E=#2980b9 (in-house/make), F=#e67e22 (external/buy), X=#888 -->
  <!-- HALB with F = ❌ FAIL (will generate PR not planned order) -->
  <!-- FERT/HALB with ND = ❌ FAIL -->
  <!-- HAWA with ND = ⚠️ WARN (still gets PR from demand, but best practice is PD) -->
  <!-- Fix path note: use enable_plant_production(mrp_type='PD', mrp_controller=<grounded>), NOT update_material or extend_to_plant -->

  <!-- SUMMARY FOOTER -->
  <div style="padding:10px 16px;background:#f4f7fb;border-top:2px solid #1a3c5e;display:flex;gap:16px;align-items:center;flex-wrap:wrap">
    <span style="font-weight:bold;font-size:14px">OVERALL VERDICT:</span>
    <span style="background:{{verdict_color}};color:white;border-radius:6px;padding:4px 16px;font-size:14px;font-weight:bold">{{verdict}}</span>
    <span style="color:#555;font-size:12px">✅ {{pass_count}} passed &nbsp; ❌ {{fail_count}} failed &nbsp; ⚠️ {{warn_count}} warnings</span>
  </div>

  <!-- GAPS (shown only if verdict != PASS) -->
  <!-- if fail_count > 0 or warn_count > 0: -->
  <div style="padding:8px 16px;background:#fff3f3;border-top:1px solid #f5c6c6;font-size:12px;color:#a00">
    <strong>Gaps / Warnings:</strong> {{gap_list}}
  </div>
  <!-- /if -->

  <div style="background:#1a3c5e;color:white;padding:6px 16px;font-size:11px;text-align:right">
    SAP S/4HANA · Genesis Verification · Plant {{plant}} · {{timestamp}}
  </div>

</div>
```

## Verdict colour values
| Verdict | verdict_color |
|---------|--------------|
| PASS    | #27ae60      |
| WARN    | #e67e22      |
| FAIL    | #c0392b      |

## Type badge colours
| Type  | type_color |
|-------|------------|
| FERT  | #1a3c5e    |
| HALB  | #2980b9    |
| HAWA  | #27ae60    |
| ROH   | #888888    |

## MRP Type badge colours
| MRPType | mrptype_color | Meaning |
|---------|---------------|---------|
| PD      | #27ae60       | Active planning — REQUIRED |
| ND      | #c0392b       | No planning — SILENT KILL |
| blank   | #888888       | Unknown / not set |

## Procurement Type badge colours (Check 7 only)
| ProcType | proctype_color | Meaning |
|----------|----------------|---------|
| E        | #2980b9        | In-house manufacture — correct for FERT/HALB |
| F        | #e67e22        | External procurement — correct for HAWA, WRONG for HALB |
| X        | #888888        | Both — special cases |
