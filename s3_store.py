"""S3 persistence for the rig: session/lesson/skill state survives an ephemeral CF push.

Design (Phase 1, runtime/design-time split):
  d2m/runtime/sessions/<id>/...   <- per-session state (trace.jsonl, summary.md, activity.jsonl, assets/)
  d2m/design/learning/<file>      <- lessons.jsonl / promotions.jsonl / learning_ledger.jsonl
  d2m/design/skills/<...>         <- promoted skills

  * hydrate()        -- on boot: pull runtime + design from S3 into the local FS (so the file-based
                        Session / learning code works unchanged). faiss is NOT synced -- learning.py
                        rebuilds it from lessons.jsonl.
  * persist_turn(s)  -- at the turn boundary (off the hot path): push the current session's changed
                        files + the design files. Skips unchanged files (local size/mtime cache) and
                        never syncs internal "orch-" sub-agent sessions.

Everything is best-effort: any S3 failure is logged and swallowed -- persistence must never break a turn
or a boot. All no-ops unless S3_PERSIST is on AND S3_BUCKET is set.
"""
import os
import sys
import json
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

_PERSIST = os.getenv("S3_PERSIST", "off").lower() in ("1", "on", "true", "yes")
_BUCKET = os.getenv("S3_BUCKET", "").strip()
_REGION = os.getenv("S3_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-west-1"
_PREFIX = os.getenv("S3_PREFIX", "d2m").strip("/")
ENABLED = bool(_PERSIST and _BUCKET)

_HERE = Path(__file__).resolve().parent
SESSIONS_DIR = Path(os.getenv("RIG_SESSIONS_DIR", "sessions"))
_LEARN_FILES = ["lessons.jsonl", "promotions.jsonl", "learning_ledger.jsonl"]
_SKILLS_DIR = _HERE / "skills"
_SYNC_STATE = _HERE / ".s3sync.json"          # {s3_key: [size, mtime]} -- skip re-uploading unchanged files

_client = None


def _log(msg):
    print(f"[s3_store] {msg}", file=sys.stderr, flush=True)


def _s3():
    global _client
    if _client is None:
        import boto3
        _client = boto3.client("s3", region_name=_REGION)
    return _client


def _load_sync() -> dict:
    try:
        return json.loads(_SYNC_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_sync(d: dict):
    try:
        _SYNC_STATE.write_text(json.dumps(d), encoding="utf-8")
    except Exception:
        pass


def _runtime_key(rel: str) -> str:
    return f"{_PREFIX}/runtime/{rel}"


def _design_key(rel: str) -> str:
    return f"{_PREFIX}/design/{rel}"


# --- upload (skip unchanged via size+mtime cache) ------------------------------------------------
def _upload(local: Path, key: str, sync: dict) -> bool:
    try:
        st = local.stat()
    except OSError:
        return False
    sig = [st.st_size, int(st.st_mtime)]
    if sync.get(key) == sig:
        return False                               # unchanged since last upload
    try:
        _s3().upload_file(str(local), _BUCKET, key)
        sync[key] = sig
        return True
    except Exception as e:
        _log(f"upload failed {key}: {e}")
        return False


def persist_session(session) -> int:
    """Push ONE session's changed files to d2m/runtime/sessions/<id>/... . Sub-agent ('orch-') sessions
    are never synced. Returns the number of files uploaded."""
    if not ENABLED or str(session.id).startswith("orch-"):
        return 0
    sdir = Path(session.dir)
    if not sdir.exists():
        return 0
    sync = _load_sync()
    n = 0
    for f in sdir.rglob("*"):
        if f.is_file() and f.name != ".s3sync.json":
            rel = f"sessions/{session.id}/{f.relative_to(sdir).as_posix()}"
            n += _upload(f, _runtime_key(rel), sync)
    _save_sync(sync)
    return n


def persist_design() -> int:
    """Push the learning files + promoted skills to d2m/design/... . Returns files uploaded."""
    if not ENABLED:
        return 0
    sync = _load_sync()
    n = 0
    for name in _LEARN_FILES:
        p = _HERE / name
        if p.exists():
            n += _upload(p, _design_key(f"learning/{name}"), sync)
    if _SKILLS_DIR.exists():
        for f in _SKILLS_DIR.rglob("*"):
            if f.is_file():
                n += _upload(f, _design_key(f"skills/{f.relative_to(_SKILLS_DIR).as_posix()}"), sync)
    _save_sync(sync)
    return n


def persist_turn(session):
    """Turn-boundary hook (best-effort): persist the current session + design. Never raises."""
    if not ENABLED:
        return
    try:
        ns, nd = persist_session(session), persist_design()
        if ns or nd:
            _log(f"persisted: session={ns} design={nd} file(s)")
    except Exception as e:
        _log(f"persist_turn failed: {e}")


def persist_all() -> dict:
    """One-shot full sweep: every non-orch session + design. For initial seeding of the bucket."""
    if not ENABLED:
        return {"enabled": False}
    sessions = 0
    if SESSIONS_DIR.exists():
        for d in SESSIONS_DIR.iterdir():
            if d.is_dir() and not d.name.startswith("orch-") and (d / "trace.jsonl").exists():
                class _S:                          # minimal Session-shape for persist_session
                    id, dir = d.name, d
                sessions += persist_session(_S())
    design = persist_design()
    return {"enabled": True, "session_files": sessions, "design_files": design}


# --- hydrate (boot) ------------------------------------------------------------------------------
def _download_if_newer(key, last_modified, size, local: Path, sync: dict) -> bool:
    """Download key->local unless the local file already MATCHES S3 (same size) and is at least as new
    (avoid clobbering newer local state during a mid-run re-hydrate). The SIZE guard is essential: a fresh
    `cf push` stamps the OLD bundled file with a NEW mtime, so an mtime-only check would silently keep a
    STALE skill over a newer promoted one in S3. A content change shows up as a size change -> we download
    regardless of mtime, so a promoted skill can never be regressed by a deploy."""
    try:
        if local.exists():
            st = local.stat()
            if st.st_size == size and st.st_mtime + 2 >= last_modified.timestamp():
                return False                       # local matches S3 (size) and is current -> skip
        local.parent.mkdir(parents=True, exist_ok=True)
        _s3().download_file(_BUCKET, key, str(local))
        sync[key] = [size, int(local.stat().st_mtime)]
        return True
    except Exception as e:
        _log(f"download failed {key}: {e}")
        return False


def hydrate() -> dict:
    """On boot: pull runtime sessions + design files from S3 into the local FS, DOWNLOADING IN PARALLEL
    so a fat asset history doesn't blow the CF boot window. Returns counts."""
    if not ENABLED:
        return {"enabled": False}
    sync = _load_sync()
    jobs = []                                      # (key, last_modified, size, local, kind)
    try:
        pages = _s3().get_paginator("list_objects_v2")
        rp = f"{_PREFIX}/runtime/sessions/"        # -> SESSIONS_DIR/<id>/...
        for page in pages.paginate(Bucket=_BUCKET, Prefix=rp):
            for obj in page.get("Contents", []):
                sub = obj["Key"][len(rp):]
                if sub:
                    jobs.append((obj["Key"], obj["LastModified"], obj["Size"], SESSIONS_DIR / sub, "sessions"))
        dp = f"{_PREFIX}/design/"                  # learning/* -> rig root ; skills/* -> skills/
        for page in pages.paginate(Bucket=_BUCKET, Prefix=dp):
            for obj in page.get("Contents", []):
                rel = obj["Key"][len(dp):]
                if rel.startswith("learning/"):
                    local = _HERE / rel[len("learning/"):]
                elif rel.startswith("skills/"):
                    local = _SKILLS_DIR / rel[len("skills/"):]
                else:
                    continue
                jobs.append((obj["Key"], obj["LastModified"], obj["Size"], local, "design"))
    except Exception as e:
        _log(f"hydrate list failed: {e}")
        return {"enabled": True, "sessions": 0, "design": 0, "error": str(e)[:80]}

    counts = {"enabled": True, "sessions": 0, "design": 0}
    from concurrent.futures import ThreadPoolExecutor

    def _do(job):
        key, lm, sz, local, kind = job
        return kind if _download_if_newer(key, lm, sz, local, sync) else None

    try:
        with ThreadPoolExecutor(max_workers=16) as ex:   # boto3 client is thread-safe for these calls
            for r in ex.map(_do, jobs):
                if r:
                    counts[r] += 1
    except Exception as e:
        _log(f"hydrate download failed: {e}")
    _save_sync(sync)
    return counts
