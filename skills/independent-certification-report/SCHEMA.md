# Independent Certification Report — Data Schema

## From genesis / run_genesis response
| Field | Source |
|---|---|
| FG material number | .parent.material |
| FG description | .parent.description |
| Component materials[] | .components[].material, .type, .description |
| BOM ID (FG) | .bom.id |
| BOM IDs (sub-assy) | .subBoms[].id |
| Routing (FG) | .routing.group |
| Routing (sub-assy) | .subRoutings[].group |
| Production version (FG) | .productionVersion |
| PIR IDs | .pirs[].id |

## From create_demand response
| Field | Source |
|---|---|
| sales_order | .sales_order |
| demand_qty | caller parameter |

## From run_mrp response
| Field | Source |
|---|---|
| timestamp | .timestamp |
| plannedOrdersCreated | .run.plannedOrdersCreated |
| purchaseReqsCreated | .run.purchaseReqsCreated |
| errors | .run.errors |
| materials[] | .materials |
| mat | .materials[].mat |
| type | .materials[].type |
| label / description | .materials[].label |
| level | .materials[].level |
| proc | .materials[].proc (E=make, F=buy) |
| output | .materials[].output (planned_order / purchase_req) |
| exception | .materials[].exception (true = exception msg) |

## From read_routing / read_production_version / read_pir (verification pass)
| Field | Source |
|---|---|
| routing group | read_routing.group |
| production version | read_production_version.version |
| PIR number | read_pir.id |
