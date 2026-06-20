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
