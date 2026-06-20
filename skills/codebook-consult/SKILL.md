---
name: codebook-consult
description: Before classifying or coding a component, query the LIVE codebook for valid values instead of guessing.
when_to_trigger: You are about to assign a material type, product group, base unit, or any coded field, or the user mentions a code you are unsure of.
verification: The chosen value appears in list_allowed_values(field).
---

# Consult the live codebook before coding a value

Guessing a code is the buried-capability failure mode — it causes SAP errors (valuation class M3/180,
tax MG/172) and silently-wrong master data. Always ground the value against the live system:

1. Call `list_allowed_values(field)` for the field you're coding (e.g. `ProductType`, `ProductGroup`,
   `BaseUnit`). This is the authoritative codebook from the live `$metadata`/value help.
2. Pick the code whose description matches the user's intent. If none matches, **ASK** — do not invent one.
3. Record the chosen code + its meaning so the rest of the flow reuses it consistently.

Optional deterministic check — run, don't read:
`run_skill_script("codebook-consult", "check_value.py", [<field>, <value>])` exits 0 (VALID) or 1 (NOT
FOUND). The script source never enters context; only its one-line verdict does.
