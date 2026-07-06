"""Typed SESSION ANCHORS -- durable facts held as TYPED STATE, not conversation recollection.

On a large multi-turn genesis, anchor facts established early (the FG material, the plant, the declared
manifest) degrade as context fills: later actions ("create a demand and run MRP") re-ask for them or work
from fading recollection, and no reconciliation can anchor on what was PLANNED. This module fixes both:

    sessions/<id>/anchors.json = {
        "fg_material":      "12345",          # the finished good this session built
        "fg_description":   "Gaming Laptop",
        "plant":            "1710",
        "genesis_manifest": [ManifestItem…],  # the DECLARED intent (flattened spec tree), written at preview
        "created_ledger":   ["12345", …],     # what has actually been created, by id
        "spec":             {…}               # the raw genesis spec (the intended contract, read by tools)
    }

Same sidecar pattern as session_meta.py (meta.json): a small JSON file in the session folder, so it
persists locally AND rides to S3 via persist_session's rglob -- kill/reload safe, no new wiring.

Rules:
  * WRITE at genesis time -- record_preview captures the manifest (the spec the human approves);
    record_commit captures the FG number + created ledger. Never implicit in conversation.
  * READ deterministically -- the Planner takes FG/plant from here (never re-asks when present);
    the Verifier reconciles created vs genesis_manifest (web.py's end-of-genesis block).
  * A compact pinned() summary rides in model context every turn; the full manifest stays in state.
"""
import json
import re
import datetime
from dataclasses import dataclass, field, asdict
from pathlib import Path

_FILE = "anchors.json"
_DATA = "@@DATA@@"                                    # genesis result sentinel: <text>@@DATA@@<json>


@dataclass
class ManifestItem:
    """One DECLARED object of a genesis -- a node of the intended spec tree, flattened."""
    name: str = ""
    description: str = ""
    type: str = ""                                    # FERT / HALB / HAWA / ROH
    role: str = ""                                    # made / bought
    level: int = 0                                    # 0 = the FG, 1 = its components, …
    quantity: float = 1
    material: str | None = None                       # filled once created (best-effort)


@dataclass
class SessionAnchors:
    fg_material: str | None = None
    fg_description: str | None = None
    plant: str | None = None
    genesis_manifest: list = field(default_factory=list)   # [ManifestItem as dict]
    created_ledger: list = field(default_factory=list)     # [matnr str], sorted, de-duped
    spec: dict | None = None                                # the raw genesis spec (intended contract)
    updated: str | None = None


# ---- disk (the meta.json pattern: read-merge-write JSON in the session folder) ----------------
def _path(session_dir) -> Path:
    return Path(session_dir) / _FILE


def read(session_dir) -> SessionAnchors | None:
    """The typed anchors for this session, or None if no genesis has anchored anything yet."""
    p = _path(session_dir)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        known = {f for f in SessionAnchors.__dataclass_fields__}
        return SessionAnchors(**{k: v for k, v in d.items() if k in known})
    except Exception:
        return None


def write(session_dir, anchors: SessionAnchors):
    anchors.updated = datetime.datetime.now().isoformat(timespec="seconds")
    try:
        _path(session_dir).write_text(json.dumps(asdict(anchors), ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# ---- manifest: the DECLARED intent, flattened from the genesis spec tree ----------------------
def manifest_from_spec(spec: dict) -> list:
    """Flatten a genesis spec (parent + nested components, any depth) into ManifestItems. This is the
    same node set run_genesis builds -- the reconciliation baseline."""
    items = []

    def rec(n, level):
        items.append(asdict(ManifestItem(
            name=str(n.get("name") or n.get("description") or ""),
            description=str(n.get("description") or n.get("name") or ""),
            type=str(n.get("type") or ""), role=str(n.get("role") or ""),
            level=level, quantity=n.get("quantity", 1) or 1,
            material=n.get("material"))))
        for c in (n.get("components") or []):
            rec(c, level + 1)

    parent = (spec or {}).get("parent") or {}
    if parent.get("description") or parent.get("material"):
        items.append(asdict(ManifestItem(
            name=str(parent.get("description") or ""), description=str(parent.get("description") or ""),
            type=str(parent.get("type") or "FERT"), role="made", level=0,
            material=parent.get("material"))))
    for c in (spec or {}).get("components") or []:
        rec(c, 1)
    return items


# ---- capture points (called from the tool layer, deterministically) ---------------------------
def record_preview(session_dir, spec: dict):
    """Genesis PREVIEW -> anchor the DECLARED manifest (what the human is approving). A new product
    (different FG description) starts a fresh ledger; a re-preview of the same product just refreshes
    the manifest."""
    if not isinstance(spec, dict):
        return
    a = read(session_dir) or SessionAnchors()
    parent = spec.get("parent") or {}
    fg_desc = str(parent.get("description") or "") or None
    if fg_desc and (a.fg_description or "").strip().lower() != fg_desc.strip().lower():
        a.fg_material, a.created_ledger = None, []    # a different product -> new genesis scope
    a.fg_description = fg_desc or a.fg_description
    a.plant = str(parent.get("plant") or a.plant or "1710")
    a.genesis_manifest = manifest_from_spec(spec)
    a.spec = spec
    write(session_dir, a)


def _gres(result_text: str) -> dict:
    m = re.search(r"@@DATA@@(\{.*\})\s*$", str(result_text or ""), re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}


def _materials_of(gres: dict) -> list:
    """Every material number the genesis result actually recorded (parent + components +
    sub-assembly children, any depth)."""
    mats = []

    def add(m):
        if m:
            mats.append(str(m))

    add((gres.get("parent") or {}).get("material"))
    for c in gres.get("components") or []:
        add(c.get("material"))
        for ch in c.get("children") or []:
            add(ch.get("material"))

    def rec_subs(subs):
        for s in subs or []:
            add(s.get("material"))
            for ch in s.get("children") or []:
                add(ch.get("material"))
            rec_subs(s.get("subassemblies"))
    rec_subs(gres.get("subassemblies"))
    return mats


def record_commit(session_dir, spec: dict, result_text: str):
    """Genesis COMMIT -> anchor the FG number + fold every created material into the ledger. The
    manifest stays what the PREVIEW declared (the human-approved intent) -- if the commit spec shrank
    (e.g. the model re-composed and flattened it), reconciliation must still see the full intent. Only
    when no preview anchored a manifest (a direct confirm=true) does the commit spec become the manifest."""
    a = read(session_dir) or SessionAnchors()
    if not a.genesis_manifest and isinstance(spec, dict):
        parent = spec.get("parent") or {}
        a.fg_description = str(parent.get("description") or "") or a.fg_description
        a.genesis_manifest = manifest_from_spec(spec)
        a.spec = spec
    g = _gres(result_text)
    if g:
        a.plant = str(g.get("plant") or a.plant or "1710")
        pmat = (g.get("parent") or {}).get("material")
        if pmat:
            a.fg_material = str(pmat)
            if not a.fg_description:
                a.fg_description = str((g.get("parent") or {}).get("description") or "") or None
        add_created(session_dir, _materials_of(g), _anchors=a)
        return
    write(session_dir, a)


def add_created(session_dir, materials, _anchors: SessionAnchors | None = None):
    """Fold material numbers into the created ledger (e.g. the verify/heal loop's final anchor set)."""
    a = _anchors or read(session_dir)
    if a is None:
        return
    seen = {str(m) for m in a.created_ledger}
    seen.update(str(m) for m in (materials or []) if m)
    a.created_ledger = sorted(seen, key=lambda x: int(x) if str(x).isdigit() else 0)
    write(session_dir, a)


def spec_of(a: SessionAnchors) -> dict | None:
    """The intended-contract spec for reconciliation: the raw anchored spec when present, else a flat
    pseudo-spec rebuilt from the manifest items (enough for presence reconciliation; full field
    conformance needs the raw spec)."""
    if a is None:
        return None
    if a.spec:
        return a.spec
    if not a.genesis_manifest:
        return None
    parent = next((i for i in a.genesis_manifest if (i.get("level") or 0) == 0), None)
    comps = [{"name": i.get("name"), "description": i.get("description"), "type": i.get("type"),
              "role": i.get("role"), "quantity": i.get("quantity", 1)}
             for i in a.genesis_manifest if (i.get("level") or 0) > 0]
    out = {"components": comps}
    if parent:
        out["parent"] = {"description": parent.get("description"),
                         "type": parent.get("type") or "FERT", "plant": a.plant}
    return out


# ---- the compact forms the model actually sees -------------------------------------------------
def pinned(session_dir) -> str:
    """A short pinned block for model context: the durable facts, never the full manifest."""
    a = read(session_dir)
    if a is None or not (a.fg_material or a.fg_description or a.genesis_manifest):
        return ""
    bits = []
    if a.fg_material or a.fg_description:
        fg = " ".join(x for x in (a.fg_material, f"— {a.fg_description}" if a.fg_description else "") if x)
        bits.append(f"finished good: {fg}")
    if a.plant:
        bits.append(f"plant: {a.plant}")
    if a.genesis_manifest:
        bits.append(f"genesis manifest: {len(a.genesis_manifest)} planned objects")
    if a.created_ledger:
        bits.append(f"created ledger: {len(a.created_ledger)}")
    line = ("SESSION ANCHORS (typed state — deterministic; trust these over recollection; "
            "do NOT re-ask the user for them): " + " · ".join(bits))
    if a.genesis_manifest and a.created_ledger and len(a.created_ledger) < len(a.genesis_manifest):
        line += (f"\n⚠ created ledger ({len(a.created_ledger)}) < manifest ({len(a.genesis_manifest)}) — "
                 "completion is NOT reconciled; only the Verifier's manifest reconciliation may say complete.")
    return line


def planner_block(a: SessionAnchors) -> str:
    """The deterministic preamble for the PLANNER: FG + plant come from typed state, never a re-ask."""
    if a is None or not (a.fg_material or a.plant):
        return ""
    fg = a.fg_material or "?"
    desc = f" ({a.fg_description})" if a.fg_description else ""
    return (
        "\n\nSESSION ANCHORS (typed state, read deterministically from this session — NOT a recollection):\n"
        f"- finished good material: {fg}{desc}\n"
        f"- plant: {a.plant or '1710'}\n"
        "When the user says 'the FG' / 'the finished good' / 'it', or names no material, USE THESE — "
        "do NOT ask the user for the material or plant again. Only ask if the user names a DIFFERENT "
        "product that has no anchor.")
