# CAD → D2M Merge Brief — Phase 6 ("the agent IS the integration layer")

**Purpose:** seed a FRESH chat to merge **AgentCAD** (creation/ideation, :5005) into **D2M** (SAP master‑data
+ planning, :9001) so ONE flow runs end‑to‑end, nothing to upload:

> prompt → design (part + parameters) → 2D drawing → [approve] → 3D assembly → CAD items → PLM items →
> **D2M genesis** (SAP material + BOM + routing + PV + PIR + cost) → demand + MRP → deterministic verification.

Start the work from `D2M_MultiAgentBom` (branch `feature/bom-file-input`). Do NOT break D2M `master` (baseline).

---

## The two projects
- **AgentCAD** — `June_2026/AgentCAD`, port **5005** = `cadplm/app.py` (`python -m cadplm.app`). Python/Flask,
  **SAP AI Core (Claude 4.6 — NO 4.8 on that landscape)**, build123d/matplotlib/Three.js/FreeCAD. Multi‑agent,
  same DNA as D2M ("LLMs design/critique; deterministic tools build/measure/verify"). Pipeline:
  Designer (brief+params) → Drafter (2D matplotlib) + Vision Verifier → **[2D approval gate]** → Motion (3D
  AssemblySpec, Three.js viewer) → **[approve]** → CAD DB (part masters + eBOM) → Product Developer (PLM) →
  PLM DB. Plus an **ECM saga** (`cadplm/ecm.py`: ECR→ECN, revise vs supersede). Read
  `AgentCAD/PROJECT_BRIEF_FOR_REVIEW.md` and `AgentCAD/cadplm/sap_shape.py` first.
- **D2M** — `June_2026/D2M_MultiAgentBom`, port **9001**, branch `feature/bom-file-input` (pushed to
  github.com/MigrationProofAI/D2M_MultiAgent). uvicorn `web:app`. Genesis + planning + deterministic
  verification + **conformance** + **pre‑genesis plan card** + **metadata‑driven create passthrough**
  (type‑aware — any A_Product OData field flows from a spec attribute to SAP, no per‑field code). THIS is the
  receiving end and it is already built.

## The seam (already ~1:1)
AgentCAD emits per released design (shared S3 `d2m-eval-store` under `d2m/cad/` + `d2m/plm/`), SAP‑shaped by
`sap_shape.py`:
- `cad/<design_id>/ebom.json` — BOM lines `{ItemNumber, Component, ComponentDescription, ComponentQuantity,
  ComponentUnit, ItemCategory}` (API_BILLOFMATERIAL_SRV shape) + `product{part_number, MaterialType FERT, …}`.
- `cad/<design_id>/part_master/CAD-xxxxxx.json` — material masters: `{part_number, rev, description, qty,
  parent, classification, material, source MAKE|BUY, material_master{MaterialType FERT|HALB|HAWA, BaseUnit,
  MaterialGroup, ProcurementType E|F, ValuationClass, NetWeight, GrossWeight, WeightUnit, Volume, VolumeUnit,
  SizeDimensions, _basis}, lifecycle{…}, documents{…}}`.
- `plm/<PLM-prod>/part_spec/PLM-xxxxxx.json` — datasheet + `cad_part_number` (CAD↔PLM link) + `planning{MRPType
  PD, LotSizingProcedure, ProcurementType, SafetyStock, PlannedDeliveryTimeInDays}`.
- `meshes/assembly.step` (3D) + `assembly.dxf` (2D) — geometry attachments; `cad/registry/index.json` — thread.

**The ONE missing piece:** `cad_agent.agent.emit_to_plm_erp` is a documented STUB — *"where you'd POST each
line to SAP material + BOM create; the POST itself is left as a TODO."* **D2M genesis IS that POST.**

## The merge (work items)
1. **Adapter** `cad_to_genesis(design_id) -> spec`: map AgentCAD `ebom.json` + `part_master/*` + PLM `planning`
   → a D2M nested genesis spec `{parent:{description,type,plant,attributes}, components:[{name, description,
   type, role made|bought, quantity, vendor, price, attributes:{NetWeight, GrossWeight, WeightUnit,
   MaterialVolume, VolumeUnit, SizeOrDimensionText, DocumentIsCreatedByCAD:true, IndustryStandardName, …},
   routing:[ops]}]}`. The SAP fields map ~1:1; the CAD attributes ride D2M's **metadata passthrough** (already
   type‑aware, so `DocumentIsCreatedByCAD` boolean lands correctly). ProductGroup/ValuationClass/ProcurementType
   come from the part_master (no more D2M defaults). Routing from CAD ops if present, else D2M's single
   placeholder.
2. **Fulfil the TODO:** call D2M `run_genesis(spec, confirm=True, on_step=…)` (streams live) instead of the stub
   → SAP material + BOM + routing + PV + PIR + cost, verified by the deterministic + **conformance** gate
   (actual SAP vs the CAD‑intended spec, field by field — the CAD digital thread is now conformance‑checked).
3. **Seamless UX:** on AgentCAD final approval (:5005), hand the spec to D2M (:9001) — in‑process import OR an
   HTTP call. `AgentCAD/d2m_studio_ui_mock.html` is the intended unified UI. NO file upload, NO Excel.
4. **Digital thread end‑to‑end:** CAD part_number → SAP material number (persist the mapping); every material
   born with `DocumentIsCreatedByCAD=true` (literally true); CAD rev → `MaterialRevisionLevel` (NOTE:
   config‑gated on the header — needs the parked **view‑aware routing** to persist). ECM saga → D2M change_*
   tools (Stage‑2 change conformance).

## Already built on the D2M side (this session — the catcher)
- **Metadata‑driven create passthrough**, type‑aware: CAD attrs (weight, volume, dims, `DocumentIsCreatedByCAD`,
  `IndustryStandardName`, material) flow to SAP with no per‑field code. Proven (mat 14295).
- **Deterministic genesis + conformance** (actual SAP vs intended contract, MISSING/DRIFT, retry, ~0 tokens).
- **Pre‑genesis plan card** (tabbed contract + provenance + board) — the CAD eBOM becomes the plan the board
  reviews before commit.
- **Live per‑object streaming**, **routing reconciliation**, **work‑center validity flag (CR/084)**,
  honest defaults (material group `01`, single‑op placeholder routing).

## Constraints & gotchas
- AI Core 4.6 on AgentCAD; D2M reachable from it. Keep D2M `master` locked; merge on a branch.
- Shared S3 bucket already coexists (`d2m/cad`, `d2m/plm`, `d2m/design`).
- **Fidelity:** AgentCAD masses/volumes are ENVELOPE ESTIMATES (mm‑derived, `_basis` flag) until real STEP
  geometry lands — carry the `_basis` honesty into D2M; conformance will faithfully reflect estimate vs actual.
- Two AgentCAD tracks (mature **Studio** at 5005 vs a newer typed vertical‑slice) are NOT yet unified — use the
  **Studio** output (`cad/…`, `plm/…`) as the merge source of truth.
- Work‑center validity (CR/084) and view‑routing (CountryOfOrigin/MaterialRevisionLevel are plant‑view) still
  apply — the CAD routings must use routing‑valid work centers.

## First steps in the fresh chat
1. Read this brief + `AgentCAD/PROJECT_BRIEF_FOR_REVIEW.md` + `AgentCAD/cadplm/sap_shape.py` + a real sample
   `ebom.json` and `part_master/*.json` (run one AgentCAD design or read an existing `cadplm_store/` / S3 one).
2. Build + unit‑test the `cad_to_genesis` adapter on that sample (no SAP writes — preview via the plan card).
3. Wire the handoff (AgentCAD approval → D2M `run_genesis`), commit one, verify via conformance (CAD intent vs SAP).
4. Then the unified Studio UX.

_Related D2M memories: metadata-driven-create-passthrough · conformance-verification · pre-genesis-plan-card ·
deterministic-file-bom-commit · work-center-routing-validity · roadmap-6-phase (Phase 6)._
