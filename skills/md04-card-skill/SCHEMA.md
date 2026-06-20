# MD04 Card — Data Schema

Fields extracted from the SAP MD04 Stock/Requirements List screen (transaction MD04).

## Header Fields
| Field | SAP Label | Notes |
|-------|-----------|-------|
| material | Material | Material number |
| description | Description | Material short text |
| plant | Plant | Plant code |
| mrp_area | MRP Area | Usually = plant |
| plant_name | (next to MRP Area) | e.g. "Plant 1 US" |
| mrp_type | MRP type | PD, ND, VB, etc. |
| material_type | Material Type | FERT, HALB, HAWA, ROH… |
| base_unit | Unit | EA, KG, PC… |
| as_of | Title timestamp | "as of HH:MM hrs" |

## Line Items (MRP Elements table)
| Field | SAP Column | Notes |
|-------|-----------|-------|
| date | Date | DD.MM.YYYY |
| mrp_element | MRP el. | Stock, PldOrd, CusOrd, PurRqs, PurOrd, PrdOrd, etc. |
| element_data | MRP element data | Document number / reference |
| rescheduling | Reschedulin… | Rescheduling date if any |
| exception | E… | Exception message code |
| receipt_reqmt | Receipt/Reqmt | Positive = receipt, Negative = requirement |
| available_qty | Available Qty | Running cumulative available stock |
| prod_version | Pro… | Production version (e.g. 0001) |

## BOM Tree (left panel)
| Field | Notes |
|-------|-------|
| tree_nodes | List of material numbers shown in the pegged requirements tree |
| tree_structure | Parent → child groupings visible in the left panel |
