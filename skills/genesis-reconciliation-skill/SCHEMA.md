# SCHEMA — Genesis Reconciliation Skill

## Purpose
Produce a **Final Object Count Reconciliation** table after any `run_genesis` call.
The table compares **Planned** (from the genesis plan, confirm=false) vs **Created** (from the genesis result, confirm=true).

---

## Object Types Tracked

| # | Object Type | How Planned Count is Derived | How Created Count is Derived |
|---|---|---|---|
| 1 | Material Masters | 1 (parent FERT) + N components (HAWA/ROH/HALB) | Count of mat# returned in genesis result |
| 2 | PIRs | Count of components where role=bought (HAWA/ROH with vendor+price) | Count of PIR records returned |
| 3 | Standard Cost Records | Count of components where price > 0 | Count of cost records returned |
| 4 | BOM | 1 per parent assembly (FERT or HALB with children) | Count of BOM numbers returned |
| 5 | Routing | 1 per assembly that has a routing spec | Count of routing groups returned |
| 6 | Production Version | 1 per assembly with BOM + routing | Count of prod versions returned |
| 7 | Sales Order (Demand) | 1 if demand was requested, else 0 | 1 if SO number returned, else 0 |
| 8 | MRP Run | 1 if MRP was requested, else 0 | 1 if MRP result returned, else 0 |
| **TOTAL** | | Sum of all Planned | Sum of all Created |

---

## Result Logic
- ✅ = Created >= Planned (all objects accounted for)
- ❌ = Created < Planned (gap — escalate)
- ⚠️ = Created > Planned (unexpected extra objects — review)

---

## Data Flow

```
run_genesis(confirm=false)  →  extract PLANNED counts from plan
run_genesis(confirm=true)   →  extract CREATED counts from result
reconcile()                 →  render scorecard card
```

## Multi-Level Support
For assemblies with HALB sub-assemblies (e.g. Bicycle):
- Material Masters = 1 FERT + N HALB + M bought components
- BOMs = 1 per FERT + 1 per HALB (each with children)
- Routings = 1 per FERT + 1 per HALB
- Production Versions = 1 per FERT + 1 per HALB
- PIRs = count of bought (leaf) components only
- Standard Cost Records = count of components with price > 0
