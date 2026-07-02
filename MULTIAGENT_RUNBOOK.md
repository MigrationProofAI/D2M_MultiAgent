# D2M Multi-Agent — Runbook & Next Steps

Companion to `STARTING_POINT.md`. This is the standing reference: **how to run it, how to test it, what's
done, and what's left** to go from *"we started multi-agent"* to *"we are a multi-agent team."*

---

## 1. How to start it (every time)

Three processes. Run each from **conda base** (has pyrfc / the RFC SDK).

| Server | Port | Folder | Command | Needed for |
|---|---|---|---|---|
| **Rig (the app)** | 9000 | `D2M_MultiAgent` | `.\run_full.ps1` (sets all flags) | everything |
| **Prodver RFC** | 8002 | `MCPCTypeNWRFC` | `python sap_prodvers_mcp.py` | routing + production-version read/write |
| **Planning RFC** | 8001 | `MCPCTypeNWRFC` | `python sap_planning_mcp.py` | `create demand` / `run MRP` |

`run_full.ps1` launches the rig with the multi-agent flags:
`MODEL_PROVIDER=anthropic` · `GENESIS_DEDUP=off` · `RIG_ORCHESTRATE=on` · `RIG_HEAL_MAX=5` · `RIG_THINKING=on`.

Then open **http://localhost:9000** (Ctrl+R if you just redeployed the UI — `index.html` is `no-cache`).

**Quick health check (any time):**
```
curl -s -o /dev/null -w "%{http_code}" http://localhost:9000/      # 200 = rig up
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8002/sse   # 200 = prodver up
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001/sse   # 200 = planning up
```

---

## 2. How to test it (the standing checklist)

### A. The live golden path (in the browser, :9000)
1. **New session** → paste a BOM image → one-line prompt (state plant + which part is the made HALB).
2. Review the **preview** (nothing written).
3. Type **"go ahead"** → watch the **🔭 Agent Activity** / inline reasoning:
   - 💭 **doer** thinks + creates (FERT, HALBs, HAWAs, BOMs)
   - 🧭 **conductor** → "verifying N materials against SAP…"
   - 💭 **verifier** reads SAP back and certifies / vetoes
   - 🔧 heal passes until ✅ or an honest ❌.

### B. What "good" looks like (the acceptance checks)
- [ ] Verifier checks **only this session's fresh materials** (a tidy contiguous block, e.g. `12055–12062`) — **no day-old numbers, no out-of-range strays.**
- [ ] **No phantom-chasing** — every gap names a real object (`11758 routing`, not a bare `404`).
- [ ] Heal loop **converges** (✅ verified) or stops with an **honest** residual list — never a fake "all green."
- [ ] Certification shows **full keys**: BOM @ plant/material/usage/altbom; routing group+counter; PV verid+usage+alt; PIR supplier+price.
- [ ] **No CSRF block** on commit; **no OpenAI billing** on the hot path (see §5).

### C. The offline proofs (no browser; run any time to confirm the spine still holds)
```
python run_verify.py     # authority deny-test + verify-loop + the verifier catches a false claim
python run_board.py      # 3 bounded reviewers run concurrently + a synthesizer (the parallel shape)
python run_boardroom.py  # THE BOARDROOM: 5 function personas (Eng/Proc/Compliance/Finance/Planning) + a Chair
```

---

## 3. Where we are — the spine (DONE, proven live)

- [x] **Orchestrator seam** — `subagent()` = fresh `Session` + isolated `TieredMemory` + `run_turn`.
- [x] **Four shapes exist** (`orchestrate.py`): sequential · parallel · loop · hybrid · `run_doer_critic`.
- [x] **Loop in production** — Doer → **independent read-only Verifier** → heal, capped (`RIG_HEAL_MAX`).
- [x] **Authority enforcement** — the Verifier *structurally cannot write* (`VERIFIER_TOOLS`, deny-test passes).
- [x] **Scope anchoring** — the Verifier checks exactly the materials the Doer created (no wandering).
- [x] **Read-back tools** — material, BOM, PIR, **routing (MAPL)**, **production version (MKAL)**.
- [x] **Transparency** — inline 💭 reasoning in the chat + the agent-labelled Agent Activity chain.
- [x] **Reliability hardening** — CSRF self-heal, dedup hard-off, anchor precision, `/btw` steering, stuck-spinner watchdog.
- [x] **The BOARDROOM** (`boardroom.py` / `run_boardroom.py`) — 5 cross-functional personas (Engineering ·
      Procurement · Compliance · Finance · Planning), each a bounded **read+advise/veto** agent in its own
      memory, reviewing CONCURRENTLY (the *parallel* shape), composed by a **Chair** into one board decision
      (the *hybrid* shape). Proven live: each persona stays in its lane; the Chair applies the veto rule.

> This is the **chassis + the three shapes that matter** — the verify→heal **loop** (Doer + Verifier), the
> **boardroom** (5 function personas + Chair), and the **hybrid** that composes them. The model is
> **Claude Sonnet 4.6 on SAP AI Core** (deployment `d20b9095bde7c0ef`).

---

## 4. What's left to be *completely* multi-agent (the steps)

The vision in `STARTING_POINT.md` is a **team of domain-bounded agents**, composed by the Conductor. We have
the recipe and the chassis; this is now the mechanical part ("the 8th agent costs the same as the 3rd").

- [ ] **Step A — Split the generalist Doer into domain agents.** Start with **Material → BOM → Routing**,
      each: (1) `skills/<agent>/SKILL.md` declaring authority + allowed tools; (2) register as
      `subagent(SKILL, allowed_subset)`; (3) one line in the Conductor's plan; (4) a golden-path test + a
      **deny-test**; (5) flip its flag on.
- [ ] **Step B — Add Costing + Procurement (PIR) agents** the same way.
- [ ] **Step C — Wire the BOARDROOM into the chat** (the *hybrid*: convene the function board *inside* the
      genesis flow — at preview, the board GO/NO-GOs the plan before the human confirms). The engine is
      **built and proven** (`boardroom.py` / `run_boardroom.py`); what's left is an intent + a UI lane so it
      runs in the product, not just the script. **This is the closest "started → real" win.**
- [ ] **Step D — Generalize the router** from the binary `is_genesis` to an **N-way router** that dispatches
      to the right agent/persona.
- [ ] **Step E — Group sub-agent traces per agent** in the Agent Activity panel (lanes for doer / verifier /
      each domain agent) — partly there via the agent tags.

Each step is additive, flag-gated, and leaves the running loop intact.

---

## 5. Known follow-ups (data / honesty — not blocking the architecture)

- [ ] **PIR price one-liner** — `genesis.py` creates the PIR without passing the price (`0.01` placeholder);
      pass `net_price=c["price"]` so prices land on the PIR and the verifier passes.
- [ ] **Cut the OpenAI embeddings cord** — `mcp_server/vector.py` still calls OpenAI (`text-embedding-3-small`)
      on the hot path (`search_materials`). Repoint to an AI Core embedding deployment or local
      `sentence-transformers`. (Task #1 from `STARTING_POINT.md` — still open.)
- [ ] **Old test materials in SAP** — leftovers (the bicycle `11728`, etc.) are harmless but can be cleaned
      with a scripted delete if you want a tidy system.

---

## 6. Flags reference

| Flag | Default | Effect |
|---|---|---|
| `RIG_ORCHESTRATE` | off | on = the verify+heal multi-agent loop runs on the genesis path |
| `RIG_BOARD` | on | on = the cross-functional board convenes on each genesis **preview** (GO/NO-GO before you confirm) |
| `RIG_HEAL_MAX` | 5 | max auto-heal passes before an honest "still incomplete" |
| `RIG_THINKING` | off | on = extended thinking (the 💭 reasoning chain); costs more AI Core tokens |
| `GENESIS_DEDUP` | off | off = **always create fresh** (no reuse of old materials); hard floor — spec can't re-enable |
| `MODEL_PROVIDER` | anthropic | Claude on AI Core (no out-of-pocket spend) |
