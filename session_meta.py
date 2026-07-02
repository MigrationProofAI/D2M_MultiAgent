"""Wall-clock timestamps for a session, stored in its OWN data (meta.json) -- NOT file mtimes.

File mtimes are unreliable: the S3 hydrate rewrites them to boot time on every CF push, collapsing the
Sessions dropdown to "all the same time". So we stamp the REAL time at each turn into the session folder:

    meta.json = {"created": <ISO, set once>, "updated": <ISO, set every turn>}

meta.json rides to S3 like any other session file, so the time survives a push. `times()` falls back to
None for old sessions that predate this (the caller then uses trace.jsonl mtime).
"""
import json
import datetime
from pathlib import Path


def touch(session):
    """Record the wall-clock time for this turn: meta.json created (once) + updated (now)."""
    try:
        p = Path(session.dir) / "meta.json"
        now = datetime.datetime.now().isoformat(timespec="seconds")
        meta = {}
        if p.exists():
            try:
                meta = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
        meta.setdefault("created", now)
        meta["updated"] = now
        p.write_text(json.dumps(meta), encoding="utf-8")
    except Exception:
        pass


def times(session_dir):
    """(created_iso, updated_iso) from meta.json -- wall-clock, mtime-immune. (None, None) if absent."""
    p = Path(session_dir) / "meta.json"
    if p.exists():
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
            return m.get("created"), m.get("updated")
        except Exception:
            pass
    return None, None
