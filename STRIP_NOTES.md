# STRIP_NOTES — what the clean-room rig removed vs kept

The rig is D2M with the framework stripped away, leaving only what is **load-bearing for the three
proofs** (tiered memory/compaction, skills with progressive disclosure, the learning loop). With no
harness, a failure is **ours** — and therefore fixable. The existing ADK/A2A D2M is untouched.

## Removed

**ADK framework** (the whole reason for the clean room):
- `main.py` — ADK `Runner` + WebSocket + intent router + `_TokenTrimPlugin`. Replaced by the
  hand-rolled loop in `agent.py` + `orchestrate.py`.
- `create_pipeline.py` — ADK `SequentialAgent`. Replaced by `run_sequential`.
- ADK tests: `test_agent.py`, `test_pipeline.py`, `test_router.py`, `test_trace.py`, `validate_pipeline.py`.

**A2A** — none was present. The app never used agent cards / `/.well-known` / A2A servers; only a stray
`a2a` substring lived in a dev script, removed with it. Nothing else to strip.

**Non-load-bearing D2M features** (not needed to prove the three capabilities):
- MCP feature servers: `mcp_server/{genesis,make,assurance,discipline,graph,vector}.py`.
- Rule engine: `rule_engine_glue.py`, `verdict.py`, `policies.json`, `policies.md`, `rules.md`.
- Dev scripts + data + docs: `dumpcodebook.py`, `extract.py`, `expand_material.py`, `check_material.py`,
  the remaining `test_*.py`, `*.svg`, `genesis_laptop.csv`, `expand_11070.json`, and the D2M
  `README/ARCHITECTURE/STATUS` docs. The React `frontend/` + `static*/` were excluded at copy time —
  the rig is CLI/headless (its token meter prints to stdout).

## Kept (the substance)

- `mcp_server/sap.py` — the SAP OData read/write layer (+ `plant_country.json`, `work_centers.json` it
  reads). Imported as **plain callables** in `tools.py`; the `@mcp.tool()` decorator is bypassed
  (FastMCP returns the original function), so **no MCP server runs** — the ceremony is gone, the
  substance stays.
- `learning.py` — the learning-loop engine (ported cleanly in Step 5).
- `knowledge.py` + `knowledge.md`, `code_book.json` — for the codebook-consult skill (Step 3).
- `skills/` — the progressive-disclosure skill pattern (extended in Step 3).
- `.env` (gitignored) — the same SAP public endpoint as D2M, for realism.

## New (the rig spine — code we own)

- `model_client.py` — the **model seam**: swap OpenAI / Anthropic / GenAI-Hub in one place.
- `tools.py` — SAP tools as plain callables + their JSON tool-specs.
- `agent.py` — the **hand-rolled loop**: model call → tool dispatch → repeat.
- `orchestrate.py` — `run_sequential` / `run_parallel` / `run_loop` / `run_hybrid`.

## Gate

`gate_step1.py` creates one material and reads it back through the stripped loop. Passing it means the
spine survived the strip.
