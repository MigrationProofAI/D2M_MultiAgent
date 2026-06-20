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
