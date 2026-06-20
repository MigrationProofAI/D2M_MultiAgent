---
name: material-create
description: Create a SAP material master (FERT/HALB/HAWA/ROH) correctly, with verified codes and the confirm-gate.
when_to_trigger: The user asks to create / add a new material, product, or component in SAP.
verification: get_material(new_id) returns the created material with the expected ProductType.
---

# Creating a material in SAP S/4HANA

Do these in order — do not skip the gate.

1. **Resolve coded values first.** Material type (FERT/HALB/HAWA/ROH), base unit and product group must
   be valid codes. If unsure of any code, trigger the `codebook-consult` skill or call
   `list_allowed_values(field)`. Never guess a code — guessing causes SAP errors (M3/180, MG/172).

2. **Build the payload.** Call
   `build_material_payload(description, product_type, base_unit, product_group, plant=<plant>, sales_org=<org>)`.
   It bakes in the verified defaults (valuation class by material type; the complete tax set when a sales
   view is requested), so you don't have to know them.

3. **Preview, then commit.** `create_material(fields, confirm=false)` previews the exact request — show it
   to the user. Only call `create_material(fields, confirm=true)` after explicit approval.

4. **Verify.** `get_material(<new_id>)` and confirm the ProductType + description match what was asked.

**Rule:** never write a BOM item during a create-material flow — adding components to a BOM is a separate
request, after the materials exist.
