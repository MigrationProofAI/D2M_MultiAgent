# D2M_MultiAgent — Starting Point

> Forked from `D2M_TestRig` on 2026-06-20 as a clean baseline. **`D2M_TestRig` stays frozen.**
> This project's one job: take the single-agent rig to **multi-agent** and close the initial architecture.
> Start a fresh chat here. Read this file + the three diagrams first.

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
2. Capture the golden-path fixtures (above).
3. Write `orchestrator.py` with `subagent()` + `board_parallel()`, behind `RIG_ORCHESTRATE`.
4. Smoke-test: the parallel board yields an equivalent synthesized review. Diff vs. the in-model board.
5. Commit. Then Phase 2.

## Run / environment notes (inherited)
- Run from **conda base** (has `pyrfc`) for RFC features — `uv run`/`.venv` lacks pyrfc and silently degrades grounding/config-graph/B6/codebook.
- `.venv` was **not** copied — recreate it (`uv sync`) if you use the venv path, but prefer conda base for full features.
- `.env` and `env.txt` **were copied** (real secrets, same machine). They're gitignored — keep them out of any zip/handoff. Keep `Design2Make_R00763` (the UI source) private.
- The built UI bundle is in `static_v2/`; its source lives in the sibling `Design2Make_R00763/frontend` (rebuild there → copy to `static_v2/`).
