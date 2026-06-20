# D2M_MultiAgent — Starting Point

> Forked from `D2M_TestRig` on 2026-06-20 as a clean baseline. **`D2M_TestRig` stays frozen.**
> This project's one job: take the single-agent rig to **multi-agent** and close the initial architecture.
> Start a fresh chat here. Read this file + the three diagrams first.

## What we want to achieve (north star)
Turn the single-agent rig into a **multi-agent system**: a team of **bounded agents** — each owning one
domain (material, BOM, routing, planning, costing, pricing, rendering, grounding…) — **composed by a
Conductor** using the four orchestration shapes (sequential / parallel / loop / hybrid). The architecture
must behave like a **blueprint**: adding the Nth agent is a **mechanical, low-risk** act, not a redesign.
We add **orchestration + agents on top**; we do **not** rewrite the foundation. Everything runs on **SAP
BTP / AI Core** — zero out-of-pocket model spend.

## Non-negotiable constraints
1. **AI Core / BTP only — no OpenAI keys, no money out of pocket.**
   - The brains (main loop, genesis/vision, summaries) go through the model seam (`model_complete`). With
     `MODEL_PROVIDER=anthropic` they run **Claude Sonnet on AI Core**. ✅
   - The provider **default was flipped** `openai → anthropic` in `model_client.py` (this project only), so a
     naked `python web.py` can **never** silently bill OpenAI. `run_rig.ps1` already forces `anthropic`.
   - **Two real leaks remain (TASK #1 — small, contained, do it first):**
     - `mcp_server/vector.py` — `OpenAI()` at module load + `text-embedding-3-small`. This is the **live**
       one (semantic material search). Fix: point embeddings at an **AI Core embedding deployment** (GenAI
       Hub has them) **or** a local embedder (`sentence-transformers`). No OpenAI key either way.
     - `learning.py` — reflection (`gpt-4o-mini`) + embeddings via OpenAI. **Flag-gated OFF** (`D2M_LEARNING=0`)
       so no charge today, but route it through the seam **before** enabling it.
   - **Rule for every new agent:** call the model **only** via `model_complete` (the seam); **never**
     `import openai` directly.
2. **Don't change the foundation.** `run_turn`, the `mcp_server/*` data layer, the `model_client` seam,
   `memory.py`, `session.py`, the SAP OData/RFC contracts — **reuse, never rewrite.** These are live-verified.
3. **Small, reversible increments.** New module + feature flag + golden-path test per step. The baseline
   commit is the diff anchor. **Never break the running copy.** (Full discipline in “Change-small-and-test”.)

## How to add an agent (the repeatable recipe)
An agent is fully specified by **four things** — fill them in and it slots into the Conductor:
1. **Authority** — what it may *change* (a doer), or *read + veto* (a reviewer). Exactly one domain.
2. **Skill (`skills/<agent>/SKILL.md`)** — its charter: `when_to_trigger`, the operating procedure, and the
   **explicit list of tools it is allowed to bind**.
3. **Bound tools / MCP** — the **least-privilege subset** of already-vetted callables (`tools.py` /
   `mcp_server`). Add new data-layer code *only* if the capability genuinely doesn't exist yet.
4. **Orchestration role** — where the Conductor places it: a stage in the sequence, a voice in the parallel
   board, or a generator/critic in a loop.

**Steps:** (a) write the `SKILL.md` declaring authority + allowed tools; (b) register the agent =
`subagent(system=SKILL, tools=allowed_subset)`; (c) add it to the Conductor's plan (one line); (d) add a
**golden-path test + a deny-test** (proves it can't exceed its authority); (e) flip its flag on. **No
foundation touched.** That's the whole point — the 8th agent costs the same as the 3rd.

## Agent catalog & roadmap (the architecture already implies these)
The diagrams show a subset. The same `Agent ⊃ Skill ⊃ Tools/MCP` pattern absorbs everything we already have
plus what's coming:
- **Live doer capabilities → agents:** Material · BOM · Routing · Planning · Costing.
- **Already built, not yet drawn as agents:**
  - **PIR / Procurement** — genesis already wraps the purchase-info-record → a Procurement agent.
  - **Cost price** — the cost estimate exists → the Costing agent.
  - **Render** — the `d2m-render` skill + `render_card` → a **Render agent** (results → structured-data
    cards). This is the “render half” from our earlier discussion.
  - **Grounding** — `codebook-consult` / `codebook-grounding` skills → a Grounding agent (validates field
    values before any write).
- **Future:** **Sales-price agent** (pricing condition records), an **MD04 reader** (`read_mrp_list` against
  `API_MRP_MATERIALS_SRV` — the truthful “data half” for the MD04 card), and onward.

Adding any of these is the **four-step recipe above** — never a redesign.

## The blueprint (already in this folder)
- `architecture.svg` — **where we are**: a single hand-rolled agentic loop (`run_turn`) + a binary router. Not multi-agent.
- `target_architecture.svg` — **where we're going**: `Agent ⊃ Skill ⊃ Tools/MCP`, each agent with an **authority boundary**. A Conductor orchestrates; doer agents write within their domain; review agents read + veto; the human gate sits only at the Conductor.
- `orchestration_patterns.svg` — **the four shapes** the Conductor composes agents into: sequential, parallel, loop, hybrid.

## The key idea (don't lose it)
Nothing new under the hood. **An agent = `run_turn` + an isolated `TieredMemory` + the subset of tools its Skill is allowed to bind.** The Conductor is just an orchestrator that calls `run_turn` more than once and merges results. The only genuinely *new* mechanism is **authority enforcement** — making a Skill declare which tools it may bind, and enforcing it (least privilege).

## What already exists vs. what's missing
| Pattern | Status | Note |
|---|---|---|
| Router | ✅ exists | `is_genesis` binary — generalize to N personas |
| Sequential | ✅ exists | `run_genesis` pipeline — characterize it, don't rewrite |
| Parallel | ❌ build | fan-out N `run_turn`s + synthesize (the board is the natural first one) |
| Loop | ❌ build | generator → critic → revise, with a hard cap (loop-breaker with teeth) |
| Hybrid | ❌ build | compose the above (board *inside* genesis) |
| Authority enforcement | ❌ build | the one new mechanism — Skills bind least-privilege tools |

## Time & effort estimate (focused work)
| Phase | Work | Est. |
|---|---|---|
| 0 | Orchestrator seam: `subagent(role_system, task)` helper = fresh memory + `run_turn` | ~0.5 day |
| 1 | **Parallel board**: convert in-model board → real parallel agents + synthesizer. First demonstrable multi-agent. | ~0.5–1 day |
| 2 | **Loop**: generator → critic → revise + max-N hard stop | ~0.5 day |
| 3 | **Hybrid + N-way router**: board inside the genesis sequence | ~0.5 day |
| 4 | **Authority enforcement**: SKILL.md declares allowed tools; bind least-privilege; deny-test | ~1 day |
| 5 | UI: group sub-agent traces in the Agent-Activity panel | ~0.5 day |

- **First truthful "we are multi-agent"** (Phase 0+1): **~1–1.5 days**.
- **Full closure** (all phases): **~3–4.5 days**.
- Cheap because the loop is already a clean, reusable primitive and `TieredMemory`/`Session` already isolate per-agent context. The orchestrator is a wrapper, not a rewrite.

## Change-small-and-test — the no-regression strategy
1. **Baseline first.** This folder is committed as the known-good rig (git initialised on fork). Every change is a small diff against it — `git diff` / `git stash` / revert are your safety net.
2. **Golden-path smoke test before touching anything.** Capture today's behaviour on the canonical flows and freeze them as fixtures:
   - read material → Material card
   - genesis from image → preview (no write)
   - extend-to-plant → enable_plant_production
   - a board review → synthesized verdict
   Re-run after each change and diff. If a golden path moves, you regressed.
3. **Additive, never destructive.** Build the orchestrator as a **new module** (`orchestrator.py`) behind a **new path/intent**. Leave `run_turn` and the chat path untouched — the single-agent loop stays as the fallback and the A/B control.
4. **Feature-flag it.** `RIG_ORCHESTRATE=off` by default → behaviour identical to today. Flip on to test the new path. Ship nothing that changes the default until its smoke test passes.
5. **One pattern at a time, each behind the flag, each with its own test.** Sequential (characterize the existing genesis) → parallel → loop → hybrid. Don't start the next until the current passes golden-path + its own test.
6. **The board is the safest first conversion** — its *output shape is unchanged* (a synthesized review), so nothing downstream or in the UI moves. You only swap *how* the review is produced, and can diff old-vs-new review text directly.
7. **Test authority negatively.** Don't just prove the happy path — assert the Material agent **cannot** call planning tools (a deny-test). Least privilege isn't real until the deny is enforced.
8. **The human gate is the ultimate backstop.** Nothing writes to SAP without `confirm` — so even a mis-orchestrated run is preview-only and cannot corrupt the live system. Develop against previews/sims (`run_mrp` simulates, genesis previews); exercise live writes only deliberately.

## What NOT to touch (reuse, don't rewrite)
The proven data layer (`mcp_server/sap.py`, `make.py`, `genesis.py`, `planning_client.py`), the model seam (`model_client.py`), `memory.py`, `session.py`, and the SAP OData/RFC contracts. These are live-verified. The work is *orchestration on top*, not changes underneath.

## First concrete step for the new chat
1. Confirm the baseline runs: `run_rig.ps1` (conda base — has pyrfc; `MODEL_PROVIDER=anthropic`, dedup off).
2. **Task #1 — cut the OpenAI cord:** repoint `mcp_server/vector.py` embeddings to an AI Core embedding
   deployment (or a local `sentence-transformers` model); confirm nothing on the hot path `import openai`.
   Keep `learning.py` off until it's seam-routed too. (Small, contained — do before orchestration.)
3. Capture the golden-path fixtures (above).
4. Write `orchestrator.py` with `subagent()` + `board_parallel()`, behind `RIG_ORCHESTRATE`.
5. Smoke-test: the parallel board yields an equivalent synthesized review. Diff vs. the in-model board.
6. Commit. Then Phase 2.

## Run / environment notes (inherited)
- Run from **conda base** (has `pyrfc`) for RFC features — `uv run`/`.venv` lacks pyrfc and silently degrades grounding/config-graph/B6/codebook.
- `.venv` was **not** copied — recreate it (`uv sync`) if you use the venv path, but prefer conda base for full features.
- `.env` and `env.txt` **were copied** (real secrets, same machine). They're gitignored — keep them out of any zip/handoff. Keep `Design2Make_R00763` (the UI source) private.
- The built UI bundle is in `static_v2/`; its source lives in the sibling `Design2Make_R00763/frontend` (rebuild there → copy to `static_v2/`).
- **Model provider:** default is now `anthropic` (Claude Sonnet on AI Core). `genaihub` (gpt-4o on AI Core) is the alternative; `openai` is opt-in only and to be avoided — it spends your own key. No new agent should `import openai`; always go through `model_complete`.
