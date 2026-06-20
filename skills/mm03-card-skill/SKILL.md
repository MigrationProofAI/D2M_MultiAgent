---
name: mm03-card-skill
description: Render a SAP MM03 Display Material card (Basic Data 2 view) with identity header, Other Data and Environment sections, checkbox fields, and a tab strip — mirrors the MM03 transaction screen
when_to_trigger: show MM03, MM03 card, display material, material master card, MM03 for &lt;material&gt;, display material &lt;number&gt;, show material master
---

# mm03-card-skill

Render a card from LIVE SAP data into the STRUCTURED-DATA panel (not just chat). The runtime does
NOT execute inline scripts, so YOU bind the data and the rendering goes through render_card.

## Invoke recipe
1. Call the sources named in MAPPING (run_mrp / get_material / get_bom) for the material + plant in play.
2. Bind the returned data into the SCHEMA shape using the MAPPING rules.
3. Build the card as HTML following the TEMPLATE layout (sections, colours, chips).
4. Call render_card(title=..., content=<the card HTML>). It surfaces in the Structured Data panel.

## MAPPING.md

# MM03 Card Skill — MAPPING

## How to populate the card

1. Call `get_material(material_id=<number>, full=true)` → returns the `A_Product` JSON.
2. Extract fields per SCHEMA.md.
3. Derive `material_type_desc` from `ProductType`:
   - FERT → Finished Product
   - HAWA → Trading Goods
   - ROH  → Raw Material
   - HALB → Semi-finished Product
   - DIEN → Service
   - *(other)* → show raw code
4. Checkbox fields: render ✅ if value is `true` / `"X"`, else ☐.
5. Empty / null fields: render as `—` (em-dash), never blank.
6. If `full=true` returns plant views, pick the first plant row for the plant summary strip.
7. Call `render_card(title, subtitle, content)` as the FINAL step.

## Title / Subtitle pattern
- title:    `MM03 — Display Material · {Product}`
- subtitle: `{ProductDescription} ({material_type_desc})`

## Trigger phrases
- "show MM03", "MM03 card", "display material", "material master card",
  "show material master", "MM03 for <material>", "display material <number>"


## SCHEMA.md

# MM03 Card Skill — SCHEMA

## Source
SAP MM03 / MM60 — Display Material master (transaction MM03 or API `get_material`).
The card covers the **Basic Data 2** view plus the header identity fields common to all views.

## OData Entity
`A_Product` (header) — retrieved via `get_material(material_id, full=true)`

## Fields captured

### Identity (header bar)
| SAP Label | OData Field | Notes |
|-----------|-------------|-------|
| Material | `Product` | material number |
| Descr. | `ProductDescription` | first language |
| Material type | `ProductType` | e.g. FERT, HAWA, ROH, HALB |
| Material type desc | *(derived)* | FERT→Finished Product, HAWA→Trading Goods, ROH→Raw Material, HALB→Semi-finished |

### Tab: Basic Data 1 (summary only)
| SAP Label | OData Field |
|-----------|-------------|
| Base Unit of Measure | `BaseUnit` |
| Material Group | `ProductGroup` |
| Division | `Division` |
| Gross Weight | `GrossWeight` |
| Net Weight | `NetWeight` |
| Weight Unit | `WeightUnit` |
| Country of Origin | `CountryOfOrigin` |

### Tab: Basic Data 2 — Other Data section
| SAP Label | OData Field | Notes |
|-----------|-------------|-------|
| Prod./insp. memo | `InspectionMemo` | free text |
| Ind. Std Desc. | `IndustrialStandardDescription` | |
| Page format | `PageFormatForProductionResources` | |
| CAD Indicator | `CADDrawingNumber` | checkbox (X / blank) |
| Basic material | `BasicMaterial` | |
| MS Book Part Number | `MSBookPartNumber` | |
| Medium | `StorageConditions` | |

### Tab: Basic Data 2 — Environment section
| SAP Label | OData Field | Notes |
|-----------|-------------|-------|
| DG indicator profile | `DangerousGoodsIndicatorProfile` | |
| Environmentally rlvt | `IsEnvironmentallyRelevant` | checkbox |
| In bulk/liquid | `IsBulkLiquid` | checkbox |
| Highly viscous | `IsHighlyViscous` | checkbox |

### Plant extension (A_ProductPlant — optional, per plant)
| SAP Label | OData Field |
|-----------|-------------|
| Plant | `Plant` |
| MRP Type | `MRPType` |
| MRP Controller | `MRPResponsible` |
| Production Version | *(from A_ProductionVersion)* |
| Valuation Class | `ValuationClass` |


## TEMPLATE.md

# MM03 Card Skill — TEMPLATE

```html
<div style="font-family:Arial,sans-serif;max-width:860px;border:1px solid #c8d0da;border-radius:8px;overflow:hidden">

  <!-- ═══ SAP TITLE BAR ═══ -->
  <div style="background:#1a3c5e;color:white;padding:11px 16px;display:flex;justify-content:space-between;align-items:center">
    <div>
      <span style="font-size:17px;font-weight:bold">Display Material {{Product}} ({{material_type_desc}})</span>
    </div>
    <div style="font-size:11px;opacity:0.8">SAP S/4HANA · MM03 · Basic Data 2</div>
  </div>

  <!-- ═══ MATERIAL IDENTITY STRIP ═══ -->
  <div style="background:#f4f7fb;padding:9px 16px;display:grid;grid-template-columns:repeat(5,1fr);gap:8px;border-bottom:1px solid #d0d0d0">
    <div><div style="font-size:10px;color:#666">MATERIAL</div><div style="font-weight:bold;font-size:15px">{{Product}}</div></div>
    <div><div style="font-size:10px;color:#666">DESCRIPTION</div><div style="font-weight:bold">{{ProductDescription}}</div></div>
    <div><div style="font-size:10px;color:#666">TYPE</div><div><span style="background:#1a3c5e;color:white;border-radius:3px;padding:1px 7px;font-size:11px">{{ProductType}}</span> {{material_type_desc}}</div></div>
    <div><div style="font-size:10px;color:#666">BASE UNIT</div><div>{{BaseUnit}}</div></div>
    <div><div style="font-size:10px;color:#666">PRODUCT GROUP</div><div>{{ProductGroup}}</div></div>
  </div>

  <!-- ═══ TAB STRIP (static, Basic data 2 active) ═══ -->
  <div style="background:#e8edf3;padding:0 16px;display:flex;gap:0;border-bottom:2px solid #1a3c5e;font-size:12px">
    <div style="padding:7px 14px;color:#555;cursor:default">Basic data 1</div>
    <div style="padding:7px 14px;background:white;color:#1a3c5e;font-weight:bold;border-top:2px solid #1a3c5e;border-left:1px solid #c8d0da;border-right:1px solid #c8d0da;margin-top:2px">Basic data 2</div>
    <div style="padding:7px 14px;color:#555;cursor:default">Sales: sales org. 1</div>
    <div style="padding:7px 14px;color:#555;cursor:default">Sales: sales org. 2</div>
    <div style="padding:7px 14px;color:#555;cursor:default">Sales: General/Plant</div>
    <div style="padding:7px 14px;color:#555;cursor:default">Intl Trade: Export</div>
  </div>

  <!-- ═══ BASIC DATA 1 SUMMARY (collapsed ribbon) ═══ -->
  <div style="background:#fafbfc;padding:6px 16px;border-bottom:1px solid #e8edf3;font-size:11px;color:#555;display:flex;gap:24px">
    <span><strong>Gross Wt:</strong> {{GrossWeight}} {{WeightUnit}}</span>
    <span><strong>Net Wt:</strong> {{NetWeight}} {{WeightUnit}}</span>
    <span><strong>Division:</strong> {{Division}}</span>
    <span><strong>Country of Origin:</strong> {{CountryOfOrigin}}</span>
  </div>

  <!-- ═══ SECTION: OTHER DATA ═══ -->
  <div style="padding:14px 16px 6px 16px">
    <div style="font-size:13px;font-weight:bold;color:#1a3c5e;border-bottom:1px solid #dde3ea;padding-bottom:4px;margin-bottom:10px">Other Data</div>
    <div style="border:1px solid #d0d0d0;border-radius:4px;padding:12px 16px;display:grid;grid-template-columns:1fr 1fr;gap:10px 32px;font-size:13px">
      <div><span style="color:#666">Prod./insp. memo:</span> <strong>{{InspectionMemo}}</strong></div>
      <div><span style="color:#666">Ind. Std Desc.:</span> <strong>{{IndustrialStandardDescription}}</strong></div>
      <div><span style="color:#666">Page format:</span> <strong>{{PageFormatForProductionResources}}</strong></div>
      <div><span style="color:#666">CAD Indicator:</span> <strong>{{CADDrawingNumber_checkbox}}</strong></div>
      <div style="grid-column:1/-1"><span style="color:#666">Basic material:</span> <strong>{{BasicMaterial}}</strong></div>
      <div><span style="color:#666">MS Book Part Number:</span> <strong>{{MSBookPartNumber}}</strong></div>
      <div><span style="color:#666">Medium:</span> <strong>{{StorageConditions}}</strong></div>
    </div>
  </div>

  <!-- ═══ SECTION: ENVIRONMENT ═══ -->
  <div style="padding:14px 16px 14px 16px">
    <div style="font-size:13px;font-weight:bold;color:#1a3c5e;border-bottom:1px solid #dde3ea;padding-bottom:4px;margin-bottom:10px">Environment</div>
    <div style="border:1px solid #d0d0d0;border-radius:4px;padding:12px 16px;display:grid;grid-template-columns:1fr 1fr;gap:10px 32px;font-size:13px">
      <div><span style="color:#666">DG indicator profile:</span> <strong>{{DangerousGoodsIndicatorProfile}}</strong></div>
      <div><span style="color:#666">Environmentally rlvt:</span> <strong>{{IsEnvironmentallyRelevant_checkbox}}</strong></div>
      <div><span style="color:#666">In bulk/liquid:</span> <strong>{{IsBulkLiquid_checkbox}}</strong></div>
      <div><span style="color:#666">Highly viscous:</span> <strong>{{IsHighlyViscous_checkbox}}</strong></div>
    </div>
  </div>

  <!-- ═══ FOOTER ═══ -->
  <div style="background:#1a3c5e;color:white;padding:6px 16px;font-size:11px;display:flex;justify-content:space-between">
    <span>SAP S/4HANA · Transaction MM03</span>
    <span>Material {{Product}} · {{ProductType}} · {{ProductGroup}}</span>
  </div>

</div>
```

## Placeholder key
| Placeholder | Source field | Fallback |
|-------------|-------------|----------|
| `{{Product}}` | `Product` | — |
| `{{ProductDescription}}` | `ProductDescription` | — |
| `{{ProductType}}` | `ProductType` | — |
| `{{material_type_desc}}` | derived | raw code |
| `{{BaseUnit}}` | `BaseUnit` | EA |
| `{{ProductGroup}}` | `ProductGroup` | — |
| `{{GrossWeight}}` | `GrossWeight` | — |
| `{{NetWeight}}` | `NetWeight` | — |
| `{{WeightUnit}}` | `WeightUnit` | — |
| `{{Division}}` | `Division` | — |
| `{{CountryOfOrigin}}` | `CountryOfOrigin` | — |
| `{{InspectionMemo}}` | `InspectionMemo` | — |
| `{{IndustrialStandardDescription}}` | `IndustrialStandardDescription` | — |
| `{{PageFormatForProductionResources}}` | `PageFormatForProductionResources` | — |
| `{{CADDrawingNumber_checkbox}}` | `CADDrawingNumber` → ✅/☐ | ☐ |
| `{{BasicMaterial}}` | `BasicMaterial` | — |
| `{{MSBookPartNumber}}` | `MSBookPartNumber` | — |
| `{{StorageConditions}}` | `StorageConditions` | — |
| `{{DangerousGoodsIndicatorProfile}}` | `DangerousGoodsIndicatorProfile` | — |
| `{{IsEnvironmentallyRelevant_checkbox}}` | `IsEnvironmentallyRelevant` → ✅/☐ | ☐ |
| `{{IsBulkLiquid_checkbox}}` | `IsBulkLiquid` → ✅/☐ | ☐ |
| `{{IsHighlyViscous_checkbox}}` | `IsHighlyViscous` → ✅/☐ | ☐ |

