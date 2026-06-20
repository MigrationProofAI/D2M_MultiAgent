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
