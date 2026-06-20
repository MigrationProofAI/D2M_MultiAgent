"""promote.py -- human-gated promotion ACCEPTANCE: turn queued lessons into durable behaviour.

learning.py CAPTURES corrections and QUEUES promotions, but nothing actions them -- the queue
accumulates, it never graduates. This is the acceptance step that closes "captured -> durable".

PRINCIPLE (same as 'code decides WHEN, the model only supplies CONTENT'): the model only SUGGESTED a
lesson_type; the HUMAN re-types and confirms. Nothing is auto-applied -- a wrong auto-promoted lesson
becomes a permanent wrong rule. Every artifact is PROPOSED and shown; it goes live only on explicit
confirmation, then the promotion is marked `applied` (or `rejected`) so it leaves the queue.

Routing by the (re-typed) type:
  method  -> append an instruction fragment to a named skill's SKILL.md (create the skill if absent)
  fact    -> append a rule line to rules.md
  process -> scaffold a deterministic guard STUB in guards.py (human authors predicate + severity --
             NEVER auto-authored)
  discard -> mark the promotion rejected, no write

    uv run python promote.py            # interactive review of the queued promotions
    uv run python promote.py --list     # just list the queue
"""
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()                                  # the lesson FAISS index may rebuild on load (needs the key)

import learning

_HERE = Path(__file__).resolve().parent
SKILLS_DIR = _HERE / "skills"
RULES_FILE = _HERE / "rules.md"
GUARDS_FILE = _HERE / "guards.py"
PROMO_FILE = learning.PROMO_FILE

_DEST = {"method": "skill SKILL.md (instruction fragment)", "fact": "rules.md entry",
         "process": "deterministic guard stub (guards.py)", "discard": "rejected (no write)"}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today():
    return datetime.now(timezone.utc).date().isoformat()


def _lessons_by_id():
    learning._load()
    return {le.get("id"): le for le in (learning._lessons or [])}


def queued():
    """Queued promotions joined with their underlying lesson + the model's auto-type."""
    by_id = _lessons_by_id()
    return [{"promo": p, "lesson": by_id.get(p.get("lesson_id"), {})}
            for p in learning.list_promotions() if p.get("status") == "queued"]


def _update_promo(promo_id: str, **fields):
    """Rewrite promotions.jsonl, updating one record (audit fields: accepted_type / status / ts)."""
    promos = learning.list_promotions()
    for p in promos:
        if p.get("id") == promo_id:
            p.update(fields)
    PROMO_FILE.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in promos),
                          encoding="utf-8")


def _set_lesson_status(lesson_id: str, status: str, reason: str = "") -> bool:
    """Mark a lesson's status (recall only surfaces 'active', so 'discarded' stops it cold)."""
    learning._load()
    changed = False
    for le in (learning._lessons or []):
        if le.get("id") == lesson_id and le.get("status") != status:
            le["status"] = status
            if reason:
                le["status_reason"] = reason
            changed = True
    if changed:
        learning._rewrite()
    return changed


def retire_discarded() -> list[str]:
    """Repair pass: any lesson behind a REJECTED promotion that is still 'active' -> mark 'discarded',
    so a discard fully removes it (the promotion lane AND fuzzy recall), not just the queue entry."""
    learning._load()
    lessons = {le.get("id"): le for le in (learning._lessons or [])}
    fixed = []
    for p in learning.list_promotions():
        if p.get("status") == "rejected":
            le = lessons.get(p.get("lesson_id"))
            if le and le.get("status") == "active":
                le["status"] = "discarded"
                le["status_reason"] = f"promotion {p['id']} discarded by human"
                fixed.append(le["id"])
    if fixed:
        learning._rewrite()
    return fixed


def _frag(item) -> str:
    le, p = item["lesson"], item["promo"]
    return (le.get("correction") or p.get("summary") or "").strip()


# ---- artifact generators: PROPOSE only. write() is a closure the caller runs ONLY on confirm. ----
def _skill_artifact(item, target):
    path = SKILLS_DIR / target / "SKILL.md"
    lid = item["lesson"].get("id", item["promo"].get("lesson_id", "?"))
    fragment = f"- **promoted {lid} ({_today()})**: {_frag(item)}\n"
    if path.exists():
        new_body = path.read_text(encoding="utf-8").rstrip() + "\n" + fragment
        preview = f"APPEND to {path.relative_to(_HERE)} :\n{fragment}"
    else:
        new_body = (f"---\nname: {target}\n"
                    f"description: Preconditions promoted from captured lessons; curate as needed.\n"
                    f"when_to_trigger: The user asks to create/edit a BOM, or extend materials to a plant.\n"
                    f"verification: the precondition(s) below hold before the write.\n---\n\n"
                    f"# {target} (promoted lessons)\n\nApply these before the write:\n\n{fragment}")
        preview = f"CREATE {path.relative_to(_HERE)} :\n{new_body}"
    ref = f"skills/{target}/SKILL.md"

    def write():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_body, encoding="utf-8")
        return ref
    return preview, ref, write


def _rules_artifact(item):
    lid = item["lesson"].get("id", item["promo"].get("lesson_id", "?"))
    line = f"- ({_today()}, promoted {lid}) {_frag(item)}\n"
    ref = f"rules.md (promoted {lid})"

    def write():
        with RULES_FILE.open("a", encoding="utf-8") as f:
            f.write(line)
        return ref
    return f"APPEND to rules.md :\n{line}", ref, write


def _guard_artifact(item):
    lid = item["lesson"].get("id", item["promo"].get("lesson_id", "?"))
    fn = "check_" + lid.replace("-", "_").lower()
    stub = (f"\n\ndef {fn}(ctx):\n"
            f'    """Promoted {lid} ({_today()}): {_frag(item)}\n\n'
            f"    HUMAN authors the predicate + severity below -- NEVER auto-authored.\"\"\"\n"
            f"    predicate = None   # TODO(human): the deterministic condition that must hold\n"
            f'    severity = None    # TODO(human): "fail" | "warn" -- REQUIRED, never auto-set\n'
            f"    raise NotImplementedError({fn!r} + ': author predicate + severity before enabling')\n")
    ref = f"guards.py:{fn}"

    def write():
        head = "" if GUARDS_FILE.exists() else ('"""Promoted deterministic guards. Each was a recurring '
                                                'lesson; the human authored its predicate + severity."""\n')
        with GUARDS_FILE.open("a", encoding="utf-8") as f:
            f.write(head + stub)
        return ref
    return (f"SCAFFOLD a guard stub in guards.py ({fn}); predicate + severity left for the human:\n{stub}",
            ref, write)


def propose(item, new_type, target=None):
    """(preview, ref, write) for the chosen (re-typed) destination. Nothing is written here."""
    if new_type == "method":
        return _skill_artifact(item, target or "promoted-method")
    if new_type == "fact":
        return _rules_artifact(item)
    if new_type == "process":
        return _guard_artifact(item)
    raise ValueError(f"no artifact route for type '{new_type}'")


def accept(promo_id: str, new_type: str, target: str | None = None, confirm: bool = False) -> dict:
    """Human-gated acceptance. confirm=False PREVIEWS the proposed artifact (no write). confirm=True
    records the human re-type, WRITES the artifact, then marks the promotion applied (retiring the
    soft lesson so it stops surfacing in fuzzy recall -- now durable behaviour)."""
    item = next((it for it in queued() if it["promo"]["id"] == promo_id), None)
    if not item:
        return {"error": f"no queued promotion {promo_id}"}
    if new_type == "discard":
        if not confirm:
            return {"action": "discard",
                    "preview": "mark the promotion rejected AND retire the lesson; no artifact written"}
        _update_promo(promo_id, status="rejected", rejected_ts=_now())
        # a discard removes the lesson from the loop entirely -- not just the queue. Otherwise the
        # rejected correction keeps surfacing in fuzzy recall and can re-queue on recurrence.
        _set_lesson_status(item["lesson"].get("id", ""), "discarded", f"promotion {promo_id} discarded by human")
        return {"status": "rejected", "lesson_retired": True, "promo": promo_id}
    preview, ref, write = propose(item, new_type, target)
    if not confirm:
        return {"action": new_type, "destination": ref, "preview": preview}
    _update_promo(promo_id, lesson_type=new_type, accepted_type=new_type)   # record the human's re-type
    ref = write()                                                           # the artifact goes live
    applied = learning.apply_promotion(promo_id, ref)                       # mark applied + retire the lesson
    return {"status": "applied", "promo": promo_id, "type": new_type, "artifact_ref": ref,
            "applied": bool(applied)}


# ---- interactive review view (the human re-types + confirms here) ----
def _ask(prompt, choices):
    try:
        v = input(prompt).strip().lower()
    except EOFError:
        return None
    return v if v in choices else None


def main():
    items = queued()
    if "--list" in sys.argv:
        for it in items:
            p = it["promo"]
            print(f"  {p['id']}  [{p.get('lesson_type')}]  {p.get('summary', '')[:88]}")
        print(f"\n{len(items)} queued promotion(s).")
        return
    if not items:
        print("No queued promotions.")
        return
    print(f"=== promotion review: {len(items)} queued ===")
    print("For each: re-type the lesson (the model's type is only a suggestion), preview the artifact, confirm.\n")
    for it in items:
        p, le = it["promo"], it["lesson"]
        print("-" * 80)
        print(f"{p['id']}   model-typed: {p.get('lesson_type')}")
        print(f"  summary: {p.get('summary', '')[:200]}")
        print(f"  routes:  m=method({_DEST['method']})  f=fact  p=process  d=discard  s=skip")
        c = _ask("  your type [m/f/p/d/s]: ", {"m", "f", "p", "d", "s"})
        if c in (None, "s"):
            print("  skipped.")
            continue
        new_type = {"m": "method", "f": "fact", "p": "process", "d": "discard"}[c]
        target = None
        if new_type == "method":
            try:
                target = input("  target skill name (e.g. bom-precondition): ").strip() or "promoted-method"
            except EOFError:
                target = "promoted-method"
        prev = accept(p["id"], new_type, target=target, confirm=False)
        print("\n  PROPOSED:\n  " + (prev.get("preview", "").replace("\n", "\n  ")))
        if _ask("\n  apply this? [y/n]: ", {"y", "n"}) == "y":
            res = accept(p["id"], new_type, target=target, confirm=True)
            print(f"  -> {res}")
        else:
            print("  not applied.")


if __name__ == "__main__":
    if "--retire-discarded" in sys.argv:
        fixed = retire_discarded()
        print(f"retired {len(fixed)} lesson(s) behind already-discarded promotions: {fixed}")
    else:
        main()
