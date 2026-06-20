"""A session is a FOLDER, not loose JSON. This is the disk side of tiered memory (and the foundation
Step 4 extends): every blob (image/file) is EVICTED here and referenced by path, so it never rides in
the summarisable text stream.

    sessions/<id>/
        trace.jsonl     -- the turn-by-turn record (text + asset refs, never blob bytes)
        assets/         -- evicted blobs (images, later PDFs/STEP), named by content hash
        summary.md      -- the running compacted summary
        archive/        -- full-fidelity turns evicted from the working set
"""
import os
import json
import hashlib
from pathlib import Path

SESSIONS_DIR = Path(os.getenv("RIG_SESSIONS_DIR", "sessions"))


class Session:
    def __init__(self, sid: str):
        self.id = sid
        self.dir = SESSIONS_DIR / sid
        self.assets = self.dir / "assets"
        self.archive = self.dir / "archive"
        for d in (self.dir, self.assets, self.archive):
            d.mkdir(parents=True, exist_ok=True)
        self.trace_file = self.dir / "trace.jsonl"
        self.summary_file = self.dir / "summary.md"

    # ---- blobs: bytes to disk, only a reference rides in context ----
    def add_asset(self, data: bytes, ext: str = "png") -> str:
        """Store blob bytes -> assets/<hash>.<ext>. Returns a relative reference (NOT the bytes)."""
        h = hashlib.sha1(data).hexdigest()[:12]
        p = self.assets / f"{h}.{ext}"
        if not p.exists():
            p.write_bytes(data)
        return f"assets/{h}.{ext}"

    def asset_path(self, ref: str) -> Path:
        """Resolve a reference back to disk -- perception re-loads bytes ONLY when it needs them."""
        return self.dir / ref

    def asset_exists(self, ref: str) -> bool:
        return self.asset_path(ref).exists()

    # ---- trace / summary / archive ----
    def append_trace(self, record: dict):
        with self.trace_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def write_summary(self, text: str):
        self.summary_file.write_text(text, encoding="utf-8")

    def archive_turns(self, turns: list):
        """Append full-fidelity evicted turns -- retrievable by reference, never lost."""
        with (self.archive / "evicted.jsonl").open("a", encoding="utf-8") as f:
            for t in turns:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")

    def archived_count(self) -> int:
        p = self.archive / "evicted.jsonl"
        return sum(1 for _ in p.open(encoding="utf-8")) if p.exists() else 0

    def reload_turns(self) -> list:
        """Rebuild the conversation from trace.jsonl for DISPLAY (a fresh process does exactly this).
        Text turns come back verbatim; a turn that carried a blob comes back as a lightweight
        'image attached' MARKER + the asset path -- the bytes stay on disk, never re-embedded."""
        turns = []
        if not self.trace_file.exists():
            return turns
        for line in self.trace_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            turn = {"role": r.get("role"), "text": r.get("text", "") or ""}
            ref = r.get("image_ref")
            if ref:
                turn["image"] = {"ref": ref, "on_disk": self.asset_exists(ref),
                                 "marker": f"[image attached: {ref}]"}
            turns.append(turn)
        return turns
