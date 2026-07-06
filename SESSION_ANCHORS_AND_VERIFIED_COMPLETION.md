# Two Fixes: Session Anchors (A) + Verified‑Completion Enforcement (B)

**Seed doc for a FOCUSED chat.** Start CC in `D2M_MultiAgentBom` (branch `feature/bom-file-input`). Do NOT
break `master` (frozen baseline). No new frameworks — typed state + existing dispatch/skill patterns. Every
regression is a WIRING diagnosis traced against code, not a redesign. **Do B first (urgent), then A. Do not
conflate them** — A is retrieval‑under‑load; B is the enforcement leak (the false‑all‑green the architecture
exists to prevent).

Diagnosis below was **verified against the code on 2026‑07‑05** (file:line anchors given) — trust it, but
re‑confirm a line if you edit near it.

---

## PROBLEM A — Typed session anchors (durable facts leave the model's context)

**Symptom (320‑part / 5‑level):** after genesis, follow‑ups ("create a demand for the FG and run MRP")
re‑ask for FG material / plant, or work from fading recollection.

**Confirmed root:** there is **no `SessionAnchors`**. FG/plant/manifest live implicitly in the conversation and
degrade as context fills. (`pending_bom` in `web.py` is NOT this — it's only the file‑commit path, not FG/plant.)

**Build:**
1. Typed `SessionAnchors` on the persisted session object:
   `fg_material, fg_description, plant, genesis_manifest: list[ManifestItem], created_ledger: list[str]`.
2. **Write** at genesis time (FG, plant, full manifest) — not implicit.
3. **Read deterministically** for later actions. Demand/MRP reads `fg_material`+`plant` from state — NEVER
   re‑ask, never rely on the model re‑finding them. Absent anchor (no genesis this session) → asking is correct;
   present‑but‑re‑asked → bug.
4. Anchors ride as a short pinned summary the model always sees; the full manifest stays in state, read by tools.

**Acceptance:** 320‑part session, post‑genesis, "create demand for the FG and run MRP" runs with no FG/plant
re‑ask. Kill/reload → anchors persist (S3).

---

## PROBLEM B — Verified‑completion enforcement (URGENT)

**Symptom (28‑part laptop):** maker created 15 of 28 silently; an agent narrated "all created" (false); only
manifest reconciliation (human‑invoked, by name) found the 13 missing; created materials have MARA basic view
only, no plant extension, despite a promoted skill.

### Confirmed roots (code‑grounded)
- **B‑root: verification anchors on CREATED, not a MANIFEST.** `web.py:727` `anchor = _created_materials(steps)`;
  `web.py:768/791` `verify_genesis_objects(anchor, …)`. There is **no manifest** in `genesis.py` (grep
  manifest/intended/declared = empty). So 15 created → `anchor`=15 → **15/15 ALL VERIFIED** = the false‑green.
- **KEY LEVER — conformance already does manifest reconciliation, but only for FILE genesis.**
  `mcp_server/conformance.py::verify_conformance(spec, anchor, …)` diffs ACTUAL SAP vs the intended SPEC field‑
  by‑field; wired in `web.py:~815` (`_committed_bom_path` → re‑parse the file as the manifest). The 28‑part
  laptop was an **IMAGE genesis** (`run_genesis`, no file) → conformance never ran → only the created‑anchored
  presence check ran → false‑green. **So B is largely EXTENDING conformance to ALL genesis, not new work.**
- **B2 — completion claims are not gated to the verifier.** `guide._PLATFORM_RE` matches architecture/how‑it‑
  works phrasing, NOT "is everything created?" — so that question falls to a doer/assist agent that *narrates*
  completion. Leak = no agent's completion claim routes through reconciliation.
- **B3 — NOT yet traced.** `enable_plant_production` exists (`genesis.py:846`, extends FG + work‑scheduling);
  `_create_material` (`genesis.py:~242`) passes `plant` → `build_material_payload` sets `to_Plant`. So components
  *should* get a plant view. "MARA basic only + promoted skill not firing" is a real wiring trace to RUN — do
  not assume a cause; check the actual create path and the promoted skill's binding (local→CF promotion may
  have dropped it, same shape as earlier expand/prodver/routing‑edit regressions).

### Build
- **B1 — maker reconciles its own create‑loop before claiming done.** After the loop, compare created vs
  manifest deterministically; on any gap emit typed `IncompleteCreation{planned, created, missing:[ids]}`. A
  partial create is a typed incomplete state, NEVER a silent success. (In `run_genesis` / the create loop — it
  already accumulates a per‑node report; add the count reconciliation before the success emit.)
- **B2 — reconciliation is AUTOMATIC and EXCLUSIVE.**
  - Capture the **manifest** at genesis for EVERY path — including IMAGE genesis (the `run_genesis` spec IS the
    manifest; today only the FILE path re‑derives it). Persist to `SessionAnchors.genesis_manifest`.
  - Run reconciliation **automatically at end‑of‑genesis** (extend the existing verify/heal block, `web.py:~727‑
    825`): reconcile `created_ledger` + a LIVE re‑read against `genesis_manifest` →
    `ReconciliationReport{planned, created, missing:[ids], extra:[ids], verdict}`. Reuse `conformance` /
    `object_verifier._expand_tree`; anchor on the MANIFEST, not `_created_materials`.
  - **Gate completion:** no agent may state "complete" except by surfacing a zero‑missing reconciliation. The
    Guide must not answer completion/verification questions (enforce at dispatch — it has no path to a verdict);
    route any "did everything get created / is it all there / correct?" to reconciliation. The FIRST answer is
    the truth — no second ask.
- **B3 — restore plant‑extension wiring.** Trace the promoted skill vs the create path; is its tool bound and
  firing, or did promotion drop it (materials stop at basic view)? Fix the binding, then add a reconciliation
  check: every created material has the required views for its plant, else flag.

### Acceptance
1. Force maker under‑delivery → `IncompleteCreation`, NOT success.
2. Ask "is everything created?" → no agent verdict; reconciliation runs, returns the typed report; FIRST answer
   is the truth, no second ask.
3. Created materials carry their plant extension (not basic‑only); missing‑view flagged by reconciliation.
4. A genuinely complete run reconciles to zero‑missing before any "complete" is stated.

---

## Honest framing for the PR
The architecture is not wrong — reconciliation, when invoked, found the exact gap. The defect is that
verification must be **automatic** (runs without the human asking) and **exclusive** (only the Verifier's
reconciliation may produce a completion claim; maker optimism and Guide narration may not). This session
already built the reconciliation engine (`conformance.py`); B makes it fire on every genesis and be the sole
completion authority. Related memories: `conformance-verification`, `deterministic-genesis-verifier`,
`metadata-driven-create-passthrough`, `pre-genesis-plan-card`. The Verifier re‑reads EVERY object vs the
manifest — never a sample, never the maker's word.
