---
name: genesis-verification-checklist
description: Render an explicit, row-by-row 7-check verification checklist card for every SAP object a genesis/BOM write is expected to have created — materials, BOMs, routings, production versions, PIRs, cost conditions, and MRP planability (MRPType=PD, MRP Controller, ProcurementType=E for HALBs)
when_to_trigger: show me the verification checks, run the checklist, verification checklist, what does the verifier check, is it plannable, will MRP plan the HALBs, why no planned orders, after genesis write, after BOM write, after plant extension, audit trail
---

# genesis-verification-checklist

Render a card from LIVE SAP data into the STRUCTURED-DATA panel (not just chat). The runtime does
NOT execute inline scripts, so YOU bind the data and the rendering goes through render_card.

## Invoke recipe
1. Call the sources named in MAPPING (run_mrp / get_material / get_bom) for the material + plant in play.
2. Bind the returned data into the SCHEMA shape using the MAPPING rules.
3. Build the card as HTML following the TEMPLATE layout (sections, colours, chips).
4. Call render_card(title=..., content=<the card HTML>). It surfaces in the Structured Data panel.

## SKILL.md

# genesis-verification-checklist

Render an explicit, row-by-row verification checklist card for every SAP object a genesis/BOM write is expected to have created — materials, BOMs, routings, production versions, PIRs/cost conditions, and MRP planability. Each check is shown as a named, numbered step with its tool call, the exact SAP key that proves it, and a PASS/FAIL status. Surfaces in the Structured Data panel via render_card.

## When to trigger
- User asks "show me the verification checks" / "what does the verifier check?" / "run the checklist"
- After a genesis, plant extension, or BOM write and the user wants a visible audit trail
- Any time an independent certification card is requested that shows the check *logic* as well as the result
- User asks "is it plannable?" / "will MRP plan the HALBs?" / "why no planned orders?"

## Invoke recipe
1. Identify the in-scope material numbers from context (FERT + all HALBs + all HAWAs).
2. For each CHECK below, call the stated tool and capture the result.
3. For each object, record: check name | tool called | SAP key returned | status (✅ PASS / ❌ FAIL / ⚠️ WARN).
4. Bind results into the TEMPLATE and call render_card.

## The 7 Verification Checks (run in order)

### CHECK 1 — Material Existence
- **Tool:** `get_material(material_id)`
- **Run for:** every material in scope (FERT + all HALBs + all HAWAs)
- **Pass condition:** material exists with the correct type (FERT/HALB/HAWA) and plant view
- **Fail condition:** material not found, wrong type, or no plant view at the target plant
- **Key to report:** material number + type + plant

### CHECK 2 — BOM Completeness (FERT + every HALB)
- **Tool:** `get_bom(material, plant)`
- **Run for:** FERT and EVERY HALB (NOT for HAWAs — they are leaf nodes)
- **Pass condition:** BOM header exists AND has ≥ 1 item
- **Fail condition:** no BOM found, OR BOM header with 0 items (phantom header)
- **Key to report:** plant + parent material + BOM usage + alternative + item count
- **Note:** a HALB with no BOM of its own is a classic multi-level miss — verify each sub-assembly independently

### CHECK 3 — Routing Existence (FERT + every HALB)
- **Tool:** `read_routing(material, plant)`
- **Run for:** FERT and EVERY HALB
- **Pass condition:** at least one routing group/counter returned (count > 0)
- **Fail condition:** empty result (count = 0) — routing was never created
- **Key to report:** plant + material + routing group (PLNNR) + counter (PLNAL) + type (PLNTY)

### CHECK 4 — Production Version (FERT + every HALB)
- **Tool:** `read_production_version(material, plant)`
- **Run for:** FERT and EVERY HALB
- **Pass condition:** at least one production version returned
- **Fail condition:** empty result — PV was never created
- **Key to report:** material + plant + VERID + BOM usage (STLAN) + BOM alt (STLAL)
- **Note:** a PV with blank routing fields is still valid — the BOM binding is what matters

### CHECK 5 — Purchase Info Record (every HAWA)
- **Tool:** `read_pir(material)`
- **Run for:** EVERY HAWA / bought-out component
- **Pass condition:** PIR exists with a net price > 0
- **Fail condition:** no PIR found, or PIR exists but net price = 0 / blank
- **Key to report:** material + PIR number + supplier + net price + currency

### CHECK 6 — Cost Condition / Committed Price (every HAWA)
- **Tool:** `read_cost_condition(material)`
- **Run for:** EVERY HAWA / bought-out component
- **Pass condition:** a PPR0 condition record exists with a condition rate > 0
- **Fail condition:** no condition record, or rate = 0 (price was previewed but never committed)
- **Key to report:** material + condition record number + rate + currency + validity
- **Note:** this is the REAL price MRP/POs use — the PIR NetPriceAmount field is secondary

### CHECK 7 — MRP Planability (FERT + every HALB + every HAWA)
- **Tool:** `get_material(material_id, full=true)` — inspect A_ProductPlant fields
- **Run for:** ALL materials (FERT, every HALB, every HAWA)
- **Sub-check A — MRPType:** must be `PD` (not `ND`, not blank)
  - `ND` = MRP completely switched off for this material. Even with a BOM, routing and production version, no planned order or purchase req will ever be generated. **This is the silent default from `extend_to_plant`.**
  - WARN if any material has MRPType = ND
- **Sub-check B — MRP Controller (MRPResponsible):** must be non-blank whenever MRPType = PD
  - MRPType=PD without a controller causes SAP error M3/069. Some environments silently ignore the material.
  - WARN if MRPType = PD but MRPResponsible is blank
- **Sub-check C — Procurement Type (FERT + HALB only):** must be `E` (in-house manufacture)
  - `F` (external/buy) on a HALB means MRP raises **purchase requisitions** instead of planned orders, breaking the make cascade. A HALB with ProcType=F AND a routing is contradictory.
  - FAIL if a HALB has ProcurementType = F or blank
- **Key to report:** material + MRPType + MRPResponsible + ProcurementType + plant
- **Fix path (if gaps found):**
  - Do NOT use `update_material` — MRPType/MRPResponsible live on `A_ProductPlant`, not `A_Product` (header). `update_material` will return '400 Property MRPResponsible is invalid'.
  - Do NOT use `extend_to_plant` with mrp_type — it does not accept mrp_controller and SAP will reject PD without a controller.
  - USE `enable_plant_production(material, plant, mrp_type='PD', mrp_controller=<grounded controller>)` — the only tool that correctly sets both on A_ProductPlant.
  - After fixing, re-run MRP (MD02 multi-level) to regenerate the cascade.

## Status Legend
| Symbol | Meaning |
|--------|---------|
| ✅ PASS | Independently read back and confirmed at the stated SAP key |
| ❌ FAIL | Readable but absent or wrong — a fixable gap the doer must close |
| ⚠️ WARN | Exists but with an anomaly (e.g. 0-item BOM, 0-price PIR, MRPType=ND) |
| — N/A | Check not applicable for this material type |

## Verdict Rules
- **OVERALL PASS:** all checks are ✅ or N/A, zero ❌ or ⚠️
- **OVERALL FAIL:** any ❌ present
- **OVERALL WARN:** no ❌ but one or more ⚠️


## TEMPLATE.md

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

