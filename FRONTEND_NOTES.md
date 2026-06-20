# Frontend (static_v2) — UI follow-ups

The served UI in `static_v2/` is a **pre-built Vite/React bundle**; its source lives in a **separate
frontend project (NOT in this repo)**. Each item below is backend-confirmed and needs a small change in
that frontend source, then a rebuild + copy of `dist/` → `static_v2/`. None of these are model problems.

## 1. Chat tables render as raw markdown pipes  ← priority
**Symptom:** in the CONVERSATION panel, the model's GFM tables (`| col | col |` + `|---|---|`) show as
raw pipe text. Headers, bold, and lists render fine — only tables don't.
**Cause:** the chat `<ReactMarkdown>` is missing the GFM plugin. `remark-gfm` is **already bundled**
(confirmed: `gfm` / `micromark` / `rehype` strings present in `assets/index-B_M96kns.js`, and the
Structured-Data side renders tables) — only the chat message component lacks the plugin.
**Fix (~1 line):**
```jsx
import remarkGfm from "remark-gfm";
// …
<ReactMarkdown remarkPlugins={[remarkGfm]}>{messageText}</ReactMarkdown>
```
Model-independent: Sonnet already emits valid markdown tables, so this just renders them. (Optionally
add `remark-breaks` for softer paragraph spacing.)

## 2. Reloaded sessions lose the Agent Activity + Structured Data panels
**Symptom:** opening a past session restores the chat, but AGENT ACTIVITY (middle) and STRUCTURED DATA
(right) are empty.
**Cause:** the live `trace` + `data` (cards) are pushed **once** over the WebSocket per turn; reload only
fetches `/api/sessions/{id}/events` (chat). The two side panels are never rebuilt on reload.
**Fix:** on session open, also `GET /api/sessions/{id}/trace` and render it into AGENT ACTIVITY; for
STRUCTURED DATA, re-derive cards from the trace's tool_result `@@DATA@@` blocks (same logic as
`web.py._cards`). Backend assist if wanted: add a `/api/sessions/{id}/data` endpoint that runs `_cards`
over the persisted steps so the frontend can call it on reload.

## 3. Card renderers for non-genesis kinds
**Context:** `web.py._cards` now forwards **every** tool's `@@DATA@@` card (not just `genesis` /
`get_material`) — backend done. The panel renders genesis + material cards today; confirm/add renderers
for the other `kind`s now flowing: `bom`, `routing`, `enable` (enable_plant_production), PIR/cost,
demand/MRP. Unknown kinds should fall back to a generic key/value card rather than being dropped.
