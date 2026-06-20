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
