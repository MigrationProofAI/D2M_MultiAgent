# BOM Display Card — Data Schema

Fields extracted from SAP CS03 / MM03 BOM Display screen ("Display material BOM: General Item Overview").

## Header Fields
| Field | SAP Label | Notes |
|-------|-----------|-------|
| material | Material | Material number, e.g. 11813 |
| description | (next to material field) | Material short text, e.g. "Skateboard Complete Assembly" |
| plant | Plant | Plant code, e.g. 1710 |
| plant_name | (next to plant code) | e.g. "Plant 1 US" |
| alternative_bom | Alternative BOM | Usually 1 |
| bom_number | BOM Number | Internal BOM doc number, e.g. 00000524 |
| valid_from | Valid From | Validity start date |
| valid_to | Valid To | Validity end date |

## Line Item Fields (BOM Components)
| Field | SAP Column | Notes |
|-------|-----------|-------|
| item | Item | Item number, e.g. 0010, 0020 |
| item_category | ICt | L = stock item, N = non-stock, D = document, T = text |
| component | Component | Component material number |
| component_description | Component description | Short text of the component |
| quantity | Quantity | BOM quantity |
| unit | Unit | Base unit of measure |
| material_type | (resolved) | FERT / HALB / HAWA / ROH |
