---
name: provenance-longtext
description: Write AI agent provenance (birth certificate) into SAP material LongText entities via direct POST to A_ProductBasicText, A_ProductPurchaseText, A_ProductPlantText in API_PRODUCT_SRV — includes post_longtext.py script
when_to_trigger: after run_genesis, after enable_plant_production, 'write provenance', 'store birth certificate', 'log agent activity to SAP', after material creation
---

# provenance-longtext

Render a card from LIVE SAP data into the STRUCTURED-DATA panel (not just chat). The runtime does
NOT execute inline scripts, so YOU bind the data and the rendering goes through render_card.

## Invoke recipe
1. Call the sources named in MAPPING (run_mrp / get_material / get_bom) for the material + plant in play.
2. Bind the returned data into the SCHEMA shape using the MAPPING rules.
3. Build the card as HTML following the TEMPLATE layout (sections, colours, chips).
4. Call render_card(title=..., content=<the card HTML>). It surfaces in the Structured Data panel.

## MAPPING.md

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


## SKILL.md

# provenance-longtext

Write AI agent provenance (birth certificate) into SAP material LongText entities via direct POST to A_ProductBasicText, A_ProductPurchaseText, A_ProductPlantText, A_ProductInspectionText in API_PRODUCT_SRV.

## When to trigger
- After any run_genesis or enable_plant_production completes
- When user says 'write provenance', 'store birth certificate', 'log agent activity to SAP'
- After any material creation where AI decisions should be recorded

## Confirmed live entities (from $metadata)
- A_ProductBasicText (keys: Product, Language) — cross-plant, general notes
- A_ProductPurchaseText (keys: Product, Language) — sourcing/vendor notes
- A_ProductPlantText (keys: Product, Plant, Language) — per-plant notes
- A_ProductInspectionText (keys: Product, Language) — QA/inspection notes

## NOT available in this instance
- A_ProductInternalComment — not in $metadata (may be S/4HC version-specific)

## Write method
Direct POST to entity set (NOT PATCH via navigation on header — returns 501)

POST /sap/opu/odata/sap/API_PRODUCT_SRV/A_ProductBasicText
Content-Type: application/json
{
  "Product": "<material>",
  "Language": "EN",
  "LongText": "<provenance text>"
}

## Provenance template
See TEMPLATE.md for the standard birth certificate format.


## TEMPLATE.md

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


## post_longtext.py

import sys, json, requests, os

material = sys.argv[1]
language = sys.argv[2]
entity   = sys.argv[3]
text     = sys.argv[4]

base = os.environ.get('SAP_BASE_URL', 'https://vhcals4hci.dummy.nodomain:44301')
url  = f"{base}/sap/opu/odata/sap/API_PRODUCT_SRV/{entity}"

headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}

payload = {
    'Product': material,
    'Language': language,
    'LongText': text
}

auth = (
    os.environ.get('SAP_USER', 'DEVELOPER'),
    os.environ.get('SAP_PASS', 'ABAPtr1909!')
)

resp = requests.post(url, json=payload, headers=headers, auth=auth, verify=False)
print(json.dumps({'status': resp.status_code, 'body': resp.text[:500]}))

