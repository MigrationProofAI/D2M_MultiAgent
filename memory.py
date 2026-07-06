"""Tiered memory / context compaction -- the time-bomb fix. Three tiers:

  working  -- recent turns, verbatim, in context
  summary  -- older turns compressed to a running summary (a STRONGER model does the summary call)
  archive  -- full-fidelity turns on disk (session.archive), retrievable by reference

Compaction triggers on TOKEN BUDGET, not turn count (the budget is the real constraint; turn count
misses fat turns). CRITICAL: images/files never enter the summarisable text stream -- when one
arrives, its bytes are EVICTED to the session's assets/ and only a lightweight reference rides in
context. Summarise the prose; evict the blobs.
"""
from model_client import summarize

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("o200k_base")
    def ntok(s) -> int:
        return len(_ENC.encode(s if isinstance(s, str) else str(s)))
except Exception:                                   # offline / no tiktoken -> rough fallback
    def ntok(s) -> int:
        return len(str(s)) // 4


_SUMMARY_SYS = (
    "You maintain a running summary that compacts an ongoing agent session so older turns can be "
    "dropped from context. PRESERVE concrete facts, names, numbers, IDs, codenames, decisions, and "
    "anything needed to answer a later question. Do not editorialise. Be terse. Return ONLY the "
    "updated summary text.")


class TieredMemory:
    def __init__(self, session, system: str = "", budget: int = 2000, min_working: int = 4):
        self.session = session
        self.system = system
        self.working: list[dict] = []     # recent OpenAI-format messages
        self.summary: str = ""            # running summary of evicted turns
        self.budget = budget              # token budget that TRIGGERS compaction
        self.min_working = min_working    # never compact below this many recent messages
        self.archived_tokens = 0          # cumulative tokens evicted to disk

    # ---- token accounting ----
    def _mtok(self, m: dict) -> int:
        t = ntok(m.get("content") or "")
        for tc in (m.get("tool_calls") or []):
            t += ntok(tc.get("function", {}).get("arguments", ""))
        return t

    def working_tokens(self) -> int:
        return sum(self._mtok(m) for m in self.working)

    def summary_tokens(self) -> int:
        return ntok(self.summary)

    def total_tokens(self) -> int:
        return ntok(self.system) + self.summary_tokens() + self.working_tokens()

    # ---- adding turns (blobs get evicted here) ----
    def add_user(self, text: str, image: bytes = None, mime: str = "image/png"):
        if image is not None:
            ext = mime.split("/")[-1].replace("jpeg", "jpg")
            ref = self.session.add_asset(image, ext)            # bytes -> disk
            content = ((text or "").strip()
                       + f"\n[image attached: {ref} -- {len(image)} bytes on disk; re-load only if "
                         f"perception actually needs them, never every turn]")
            self.working.append({"role": "user", "content": content})
            self.session.append_trace({"role": "user", "text": text, "image_ref": ref})
        else:
            self.working.append({"role": "user", "content": text})
            self.session.append_trace({"role": "user", "text": text})

    def add_assistant(self, m: dict):
        self.working.append(m)
        if m.get("content"):
            self.session.append_trace({"role": "assistant", "text": m["content"]})

    def add_tool(self, tool_call_id: str, content: str):
        self.working.append({"role": "tool", "tool_call_id": tool_call_id, "content": str(content)[:8000]})

    # ---- the context actually sent to the model ----
    def context(self) -> list[dict]:
        msgs = []
        if self.system:
            msgs.append({"role": "system", "content": self.system})
        # SESSION ANCHORS ride PINNED (typed state from anchors.json, not recollection): the durable
        # facts -- FG material, plant, manifest/ledger counts -- survive compaction because they are
        # re-read from disk every context build, never summarised away.
        try:
            import anchors as _anchors
            pin = _anchors.pinned(self.session.dir)
            if pin:
                msgs.append({"role": "system", "content": pin})
        except Exception:
            pass
        if self.summary:
            msgs.append({"role": "system", "content": "SUMMARY of earlier turns (compacted, facts preserved):\n" + self.summary})
        return msgs + self.working

    # ---- compaction (token-budget trigger) ----
    def maybe_compact(self) -> bool:
        fired = False
        while self.total_tokens() > self.budget and len(self.working) > self.min_working:
            cut = self._safe_cut()
            if cut <= 0:
                break
            evicted = self.working[:cut]
            self.working = self.working[cut:]
            self.archived_tokens += sum(self._mtok(m) for m in evicted)
            self.session.archive_turns(evicted)                 # full fidelity to disk
            transcript = "\n".join(f"{m['role']}: {m.get('content', '')}"
                                   for m in evicted if m.get("content"))
            self.summary = summarize(
                _SUMMARY_SYS,
                f"Existing running summary:\n{self.summary or '(none yet)'}\n\n"
                f"Older turns now being archived:\n{transcript}\n\nUpdated running summary:")
            self.session.write_summary(self.summary)
            fired = True
        return fired

    def _safe_cut(self) -> int:
        """How many messages to evict from the front. Never leave the new front as an orphaned 'tool'
        message (OpenAI requires a tool result to follow its assistant tool_calls)."""
        cut = len(self.working) - self.min_working
        if cut <= 0:
            return 0
        while cut < len(self.working) and self.working[cut].get("role") == "tool":
            cut += 1                                            # don't split an assistant->tool pair
        return cut

    # ---- the per-turn token meter (the proof) ----
    def image_in_context(self) -> bool:
        return any(("base64" in (m.get("content") or "")) or m.get("_image_bytes")
                   for m in self.working)

    def meter(self) -> str:
        return (f"working: {self.working_tokens()} | summary: {self.summary_tokens()} | "
                f"archived (on disk): {self.archived_tokens} | "
                f"image in context: {'YES' if self.image_in_context() else 'NO'}")
