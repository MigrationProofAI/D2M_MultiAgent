# Provenance LongText — Birth Certificate Template

## A_ProductBasicText (primary provenance store)
```
=== AI AGENT PROVENANCE — BIRTH CERTIFICATE ===
Material: {material_id} | {description} ({product_type})
Created by: SAP MCP AI Agent (Genesis Skill)
Session ID: {session_id}
Timestamp: {timestamp}

DESIGN RATIONALE:
{design_rationale}

BOM GENESIS SUMMARY:
{bom_summary}

AGENT DECISIONS:
{agent_decisions}

PLANT COVERAGE: {plants}
LAST AGENT ACTION: {last_action}
```

## A_ProductPurchaseText (sourcing provenance)
```
=== SOURCING PROVENANCE ===
Agent: SAP MCP AI Agent | Session: {session_id}
Components sourced: {component_count}
Vendors resolved: {vendors}
Price basis: {price_basis}
```

## A_ProductPlantText (per-plant MRP provenance)
```
=== PLANT EXTENSION PROVENANCE ===
Plant: {plant} | Extended: {timestamp}
MRP Type: {mrp_type} | Controller: {mrp_controller}
Work Center: {work_center}
Production Version: {prod_version}
MRP Result: {mrp_result}
```
