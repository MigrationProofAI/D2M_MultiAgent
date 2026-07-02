# Provenance LongText — MAPPING

## Entity → Purpose
| Entity | Keys | Purpose | Visibility |
|--------|------|---------|------------|
| A_ProductBasicText | Product, Language | Full birth certificate | MM03 Basic Data |
| A_ProductPurchaseText | Product, Language | Sourcing/vendor research | MM03 Purchasing |
| A_ProductPlantText | Product, Plant, Language | Per-plant MRP notes | MM03 Plant Data |
| A_ProductInspectionText | Product, Language | QA/inspection AI notes | MM03 QM |

## Data sources
- session_id: from run_genesis or enable_plant_production response
- material_id: the created/extended material number
- bom_summary: from run_genesis planned/created counts
- mrp_result: from run_mrp response (planned orders + PRs)
- plants: from extend_to_plant / enable_plant_production calls

## Write sequence
1. POST to A_ProductBasicText (always — primary provenance)
2. POST to A_ProductPurchaseText (if components were sourced)
3. POST to A_ProductPlantText for each plant extended
4. Verify with GET on each entity
