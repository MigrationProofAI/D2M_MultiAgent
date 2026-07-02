# MAPPING — Genesis Plan & Result → Reconciliation Counts

## From genesis PLAN (confirm=false output)

| Field in Plan | Maps To |
|---|---|
| `parent` node present | +1 Material Master |
| Each entry in `components[]` | +1 Material Master each |
| Each component where role=bought OR type=HAWA/ROH | +1 PIR |
| Each component where price > 0 | +1 Standard Cost Record |
| Parent assembly (FERT) with components[] | +1 BOM |
| Each HALB component with its own children | +1 BOM each |
| `routing[]` present on parent | +1 Routing |
| Each HALB with routing | +1 Routing each |
| BOM + Routing both present on an assembly | +1 Production Version |
| `demand_qty > 0` OR demand requested | +1 Sales Order |
| MRP requested | +1 MRP Run |

## From genesis RESULT (confirm=true output)

| Field in Result | Maps To |
|---|---|
| Material numbers listed under 'Materials created' | Created Material Masters |
| PIR records listed | Created PIRs |
| Cost records listed | Created Standard Cost Records |
| BOM numbers listed (e.g. 000004XX) | Created BOMs |
| Routing group numbers listed (e.g. 5000XXXX) | Created Routings |
| Production version entries listed (e.g. 0001) | Created Production Versions |
| Sales order number present | Created Sales Orders |
| MRP result present (planned orders / PRs) | Created MRP Runs |

## TOTAL
TOTAL Planned = sum of all Planned column values
TOTAL Created = sum of all Created column values
Result = ✅ if Created == Planned, ❌ if Created < Planned, ⚠️ if Created > Planned
