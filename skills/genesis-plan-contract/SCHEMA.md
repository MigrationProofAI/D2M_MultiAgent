# Genesis Plan Contract — the typed pre-genesis report

The **deterministic** pre‑commit report a human approves. Rendered in code (`mcp_server/plan_report.py` +
`mcp_server/plan_card.py`) from `(parsed spec + live $metadata + provenance)` — same spec → identical report,
~0 LLM tokens. Surfaced as a CSS‑only **tabbed** card in the Structured‑Data panel; the **board** is the only
LLM layer, appended as the final tab. This is NOT an agent‑filled card skill — the LLM does not compose it.

## Provenance model (tagged on every value)
| Tag | Meaning |
|---|---|
| `file:<what>` | taken verbatim from the BOM (type, description, unit, vendor, price, structure, operations) |
| `derived:<rule>` | computed by a rule (ProcurementType E/F by role; ValuationClass by type; PurchOrg = plant) |
| `default:genesis` | a genesis policy default (MRPType PD, lot 1–10000, PV validity 31.12.9999, tax set, …) |
| `metadata:validated` | a passthrough field validated against A_Product `$metadata` (weights, dims, any header field) |
| `derived:SAP` | assigned by SAP at create (routing group/counter, material number) |

## Tabs = object types × key views (fields the create will write)
- **Materials** — Basic Data (ProductType `file:type`, Description `file`, BaseUnit `file/default`, ProductGroup
  `default`, IndustrySector `default`, + passthrough `metadata:validated`); Plant/MRP (MRPType, ProcurementType
  `derived:role`, MRPResponsible, AvailabilityCheck, LotSizing, lead times); Valuation (ValuationClass
  `derived:type`, StandardPrice, Currency); Sales/FERT (SalesOrg, ItemCategory, tax). Plus cost‑by‑system,
  anomaly flags, and the per‑material list.
- **PIRs** — Supplier `file:vendor`, PurchOrg `derived:plant`, NetPrice `file:price`, Currency, lead time, min qty.
- **Cost** — ConditionType PPR0, Rate `file:price`, Currency, Supplier.
- **BOMs** — parent (made node), usage 1 / alt 01, Components+Qty `file:structure`.
- **Routings** — Group/Counter `derived:SAP`, per operation WorkCenter `file:operations`, times `file/default`;
  header shows the distinct work centers exercised.
- **PVs** — Version 0001, BOM binding alt 01/usage 1, lot 1–10000, validity today..31.12.9999 (all `default`).
- **Board** — the cross‑functional GO/NO‑GO on the WHOLE plan (grounded on this report, not a truncated tree).

## Deterministic anomaly flags (in the Materials tab)
single‑source risk · missing price / missing vendor · made nodes with no explicit routing · price outliers
(>12× median) · duplicate descriptions · engineering‑attribute coverage (weight/dims/origin).

See memory `[[metadata-driven-create-passthrough]]` (why fields are `$metadata`‑validated),
`[[verification-cards-render]]` (the card mechanism), `[[deterministic-file-bom-commit]]` (the commit this
report gates).
