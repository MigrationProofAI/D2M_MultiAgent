"""AI-generated, cached session titles so the Sessions dropdown is scannable.

A title is generated ONCE per session and cached to the session folder as `title.json`; it is refreshed
only when the user-turn count grows (so a finished session never re-spends). Generation uses the model
seam's `summarize()` -> AI Core (Claude on the anthropic path); NO out-of-pocket / OpenAI spend. Any
failure returns None so the caller falls back to the first-message gist + datetime.
"""
import json
from model_client import summarize

_SYS = (
    "You name a work session in 3 to 7 words so a user can spot it in a list. Be specific: name the "
    "product/object and the action. Good: 'Quadcopter Drone Genesis + MRP'; 'Work-center lookup, plant "
    "1710'; 'Bicycle BOM price correction'. Bad: 'Run the genesis' (too vague). No quotes, no trailing "
    "period, max 7 words. Output ONLY the title."
)


def _context(session):
    """Compact (first request + outcome) context for titling, and the user-turn count."""
    turns = session.reload_turns()
    n = sum(1 for t in turns if t.get("role") == "user")
    first_user = next((t["text"].strip() for t in turns
                       if t.get("role") == "user" and t.get("text")), "")
    outcome = ""
    try:
        if session.summary_file.exists():
            outcome = session.summary_file.read_text(encoding="utf-8")[:1200]
    except Exception:
        outcome = ""
    if not outcome:                                   # no running summary yet -> use the last answer
        outcome = next((t["text"].strip() for t in reversed(turns)
                        if t.get("role") == "assistant" and t.get("text")), "")[:1200]
    ctx = f"First request:\n{first_user}\n\nWhat happened:\n{outcome}".strip()
    return ctx, n


def ensure_title(session):
    """Return a cached AI title, generating + caching if missing/stale. None on any failure."""
    cache = session.dir / "title.json"
    ctx, n = _context(session)
    if not ctx:
        return None
    try:                                              # fresh cache (same turn count) -> reuse, no spend
        if cache.exists():
            c = json.loads(cache.read_text(encoding="utf-8"))
            if c.get("turns") == n and c.get("title"):
                return c["title"]
    except Exception:
        pass
    try:
        title = (summarize(_SYS, ctx) or "").strip().strip('"').splitlines()[0][:80]
    except Exception:
        return None
    if not title:
        return None
    try:
        cache.write_text(json.dumps({"title": title, "turns": n}, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return title


def cached_title(session_dir):
    """Read a session's cached AI title WITHOUT generating (used by the fast list endpoint). None if absent."""
    tj = session_dir / "title.json"
    if tj.exists():
        try:
            return json.loads(tj.read_text(encoding="utf-8")).get("title")
        except Exception:
            return None
    return None
