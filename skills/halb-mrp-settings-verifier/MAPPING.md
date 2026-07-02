# Field Mapping — HALB MRP Settings

## A_ProductPlant (OData entity)
| Field | Value | Meaning |
|---|---|---|
| ProcurementType | "E" | In-house manufacture (make) |
| ProcurementType | "F" | External procurement (buy) — WRONG for HALB |
| ProcurementType | "X" | Both (special cases only) |

## A_ProductPlantMRPArea (OData entity)
| Field | Value | Meaning |
|---|---|---|
| MRPType | "PD" | MRP-driven planning — REQUIRED for make materials |
| MRPType | "ND" | No planning — MRP ignores this material |
| MRPResponsible | e.g. "001" | MRP Controller — mandatory with PD |

## Keys
- A_ProductPlant: {Product, Plant}
- A_ProductPlantMRPArea: {Product, Plant, MRPArea} — MRPArea = Plant code

## MRP Output by ProcurementType
| ProcType | MRP Output | Correct for |
|---|---|---|
| E | Planned Order | FERT, HALB (make) |
| F | Purchase Requisition | HAWA, ROH (buy) |
