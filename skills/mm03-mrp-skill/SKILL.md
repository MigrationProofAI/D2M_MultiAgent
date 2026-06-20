---
name: mm03-mrp-skill
description: Render a SAP MM03 Material Master card covering all 5 views: Basic Data 1, MRP 1, MRP 2, MRP 3, and Production Version — with colour-coded fields, section panels, and a tab-strip header
when_to_trigger: show MM03, show MRP tabs, show material master, show production version, MM03 card, MRP 1, MRP 2, MRP 3, display material master
---

# mm03-mrp-skill

Render a card from LIVE SAP data into the STRUCTURED-DATA panel (not just chat). The runtime does
NOT execute inline scripts, so YOU bind the data and the rendering goes through render_card.

## Invoke recipe
1. Call the sources named in MAPPING (run_mrp / get_material / get_bom) for the material + plant in play.
2. Bind the returned data into the SCHEMA shape using the MAPPING rules.
3. Build the card as HTML following the TEMPLATE layout (sections, colours, chips).
4. Call render_card(title=..., content=<the card HTML>). It surfaces in the Structured Data panel.

## MAPPING.md

# MM03 Full MRP Skill — OData Mapping

## Call 1 — Basic Data
```
GET /sap/opu/odata/sap/API_PRODUCT_SRV/A_Product('{material}')
  ?$select=Product,BaseUnit,ProductGroup,Division,ItemCategoryGroup,GrossWeight,NetWeight,WeightUnit
  &$expand=to_Description($filter=Language eq 'EN')
```

## Call 2 — MRP 1 + MRP 2
```
GET /sap/opu/odata/sap/API_PRODUCT_SRV/A_ProductPlant(Product='{material}',Plant='{plant}')
  ?$select=MRPType,MRPResponsible,MRPGroup,ABCIndicator,ReorderThresholdQuantity,
           LotSizingProcedure,MinimumLotSizeQuantity,MaximumLotSizeQuantity,AssemblyScrapPercent,
           ProcurementType,SpecialProcurementType,IsBackflushEnabled,InHouseProductionTime,
           PlannedDeliveryDurationInDays,GoodsReceiptDuration,SafetyStockQuantity,
           ServiceLevelPercent,SafetyDuration
```

## Call 3 — MRP 3
```
GET /sap/opu/odata/sap/API_PRODUCT_SRV/A_ProductPlantMRPArea(Product='{material}',Plant='{plant}',MRPArea='{plant}')
  ?$select=PeriodType,ConsumptionMode,AvailabilityCheckType,TotalReplenishmentLeadTime,
           MixedMRPIndicator,BackwardConsumptionPeriod,ForwardConsumptionPeriod
```

## Call 4 — Production Version
```
GET /sap/opu/odata/sap/API_PRODUCT_SRV/A_ProductionVersion
  ?$filter=Product eq '{material}' and Plant eq '{plant}'
  &$select=ProductionVersion,ProductionVersionText,ProductionVersionValidFrom,
           ProductionVersionValidTo,IsLocked,MinimumLotSizeQuantity,MaximumLotSizeQuantity,
           BillOfMaterialVariant,IsREMAllowed,ProductionLine,IssueStorageLocation,
           GoodsReceiptStorageLocation,DistributionKey,WarehouseNumber,StorageBin,SupplyArea
```


## SCHEMA.md

# MM03 Full MRP Skill — Schema

## OData Entities
| Entity | Key | Purpose |
|---|---|---|
| A_Product | Product | Basic Data 1 |
| A_ProductPlant | Product, Plant | MRP 1 + MRP 2 |
| A_ProductPlantMRPArea | Product, Plant, MRPArea=Plant | MRP 3 |
| A_ProductionVersion | Product, Plant, ProductionVersion | Production Version |

## Token Map

### Basic Data 1
| Token | OData Field | Label |
|---|---|---|
| {{material}} | Product | Material Number |
| {{plant}} | — (param) | Plant |
| {{description}} | to_Description/ProductDescription | Description |
| {{baseUnit}} | BaseUnit | Base Unit of Measure |
| {{materialGroup}} | ProductGroup | Material Group |
| {{division}} | Division | Division |
| {{itemCatGroup}} | ItemCategoryGroup | Item Category Group |
| {{grossWeight}} | GrossWeight | Gross Weight |
| {{netWeight}} | NetWeight | Net Weight |
| {{weightUnit}} | WeightUnit | Weight Unit |

### MRP 1 (A_ProductPlant)
| Token | OData Field | Label |
|---|---|---|
| {{mrpType}} | MRPType | MRP Type |
| {{mrpController}} | MRPResponsible | MRP Controller |
| {{mrpGroup}} | MRPGroup | MRP Group |
| {{abcIndicator}} | ABCIndicator | ABC Indicator |
| {{reorderPoint}} | ReorderThresholdQuantity | Reorder Point |
| {{lotSizingProcedure}} | LotSizingProcedure | Lot Sizing Procedure |
| {{minLotSize}} | MinimumLotSizeQuantity | Min Lot Size |
| {{maxLotSize}} | MaximumLotSizeQuantity | Max Lot Size |
| {{assemblyScrap}} | AssemblyScrapPercent | Assembly Scrap (%) |

### MRP 2 (A_ProductPlant)
| Token | OData Field | Label |
|---|---|---|
| {{procurementType}} | ProcurementType | Procurement Type |
| {{specialProcurement}} | SpecialProcurementType | Special Procurement |
| {{backflush}} | IsBackflushEnabled | Backflush |
| {{inHouseProduction}} | InHouseProductionTime | In-House Production (days) |
| {{plannedDeliveryTime}} | PlannedDeliveryDurationInDays | Planned Delivery Time (days) |
| {{goodsReceiptTime}} | GoodsReceiptDuration | Goods Receipt Time (days) |
| {{safetyStock}} | SafetyStockQuantity | Safety Stock |
| {{serviceLevel}} | ServiceLevelPercent | Service Level (%) |
| {{safetyTime}} | SafetyDuration | Safety Time (days) |

### MRP 3 (A_ProductPlantMRPArea)
| Token | OData Field | Label |
|---|---|---|
| {{periodIndicator}} | PeriodType | Period Indicator |
| {{strategyGroup}} | MRPPlanningCalendar | Strategy Group |
| {{consumptionMode}} | ConsumptionMode | Consumption Mode |
| {{availabilityCheck}} | AvailabilityCheckType | Availability Check |
| {{totalReplLeadTime}} | TotalReplenishmentLeadTime | Total Repl. Lead Time (days) |
| {{mixedMRP}} | MixedMRPIndicator | Mixed MRP |
| {{bwdConsumption}} | BackwardConsumptionPeriod | Bwd Consumption (days) |
| {{fwdConsumption}} | ForwardConsumptionPeriod | Fwd Consumption (days) |

### Production Version (A_ProductionVersion)
| Token | OData Field | Label |
|---|---|---|
| {{prodVersion}} | ProductionVersion | Version |
| {{prodVersionText}} | ProductionVersionText | Description |
| {{validFrom}} | ProductionVersionValidFrom | Valid From |
| {{validTo}} | ProductionVersionValidTo | Valid To |
| {{locked}} | IsLocked | Locked |
| {{minLotSizePV}} | MinimumLotSizeQuantity | Min Lot Size |
| {{maxLotSizePV}} | MaximumLotSizeQuantity | Max Lot Size |
| {{altBOM}} | BillOfMaterialVariant | Alternative BOM |
| {{bomUsage}} | BillOfMaterialItemNodeNumber | BOM Usage |
| {{remAllowed}} | IsREMAllowed | REM Allowed |
| {{productionLine}} | ProductionLine | Production Line |
| {{planningID}} | PlanningID | Planning ID |
| {{issueStorLoc}} | IssueStorageLocation | Issue Stor. Location |
| {{receivingLoc}} | GoodsReceiptStorageLocation | Receiving Location |
| {{distributionKey}} | DistributionKey | Distribution Key |
| {{warehouseNumber}} | WarehouseNumber | Warehouse Number |
| {{destinationBin}} | StorageBin | Destination Bin |
| {{obRefMat}} | OBRefMaterial | OB Reference Mat. |
| {{defaultSupplyArea}} | SupplyArea | Default Supply Area |
| {{targetPSA}} | TargetPSA | Target PSA |


## TEMPLATE.md

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


## fetch_mm03.js

// fetch_mm03.js — MM03 Full MRP Skill fetcher
// Usage: node fetch_mm03.js <material> <plant>
// Env: SAP_BASE_URL, SAP_USER, SAP_PASS

const https = require('https');
const [,, material, plant] = process.argv;

const base = process.env.SAP_BASE_URL;
const auth = 'Basic ' + Buffer.from(`${process.env.SAP_USER}:${process.env.SAP_PASS}`).toString('base64');
const headers = { Authorization: auth, Accept: 'application/json' };

async function get(path) {
  return new Promise((resolve, reject) => {
    const url = base + path;
    https.get(url, { headers }, res => {
      let data = '';
      res.on('data', d => data += d);
      res.on('end', () => resolve(JSON.parse(data)));
    }).on('error', reject);
  });
}

async function fetchMM03(mat, plt) {
  const [basic, plant_data, mrp3, pv] = await Promise.all([
    get(`/sap/opu/odata/sap/API_PRODUCT_SRV/A_Product('${mat}')?$expand=to_Description($filter=Language eq 'EN')&$format=json`),
    get(`/sap/opu/odata/sap/API_PRODUCT_SRV/A_ProductPlant(Product='${mat}',Plant='${plt}')?$format=json`),
    get(`/sap/opu/odata/sap/API_PRODUCT_SRV/A_ProductPlantMRPArea(Product='${mat}',Plant='${plt}',MRPArea='${plt}')?$format=json`),
    get(`/sap/opu/odata/sap/API_PRODUCT_SRV/A_ProductionVersion?$filter=Product eq '${mat}' and Plant eq '${plt}'&$format=json`)
  ]);
  return { basic: basic.d, plant: plant_data.d, mrp3: mrp3.d, versions: pv.d.results };
}

fetchMM03(material, plant).then(d => console.log(JSON.stringify(d, null, 2))).catch(console.error);

