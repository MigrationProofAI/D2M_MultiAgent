"""grounding.py -- B1: the DETERMINISTIC backstop for coded-field grounding.

The `codebook-grounding` skill ADVISES; this ENFORCES (same advisory-vs-structural split as the
loop-breaker). Before a create/extend write, every coded field in the payload must be a valid
codebook value for its field, every plant-specific value valid for the plant, and every required
coded field present -- else the write is BLOCKED here with a clear message, rather than let through
to SAP to come back as a cryptic reject (M3/180, MG/172, a missing plant field).

Whether enforcement is active + how hard comes from policies.json -> "coded_grounding" (severity from
policy, not code -- same rule as assurance.py).
"""
import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_POLICY = _HERE / "policies.json"

# coded field (OData name, as it appears in the deep-insert payload) -> codebook field to validate.
_CODED = {
    "ProductType": "ProductType", "ProductGroup": "ProductGroup", "IndustrySector": "IndustrySector",
    "BaseUnit": "BaseUnit", "MRPType": "MRPType", "ProcurementType": "ProcurementType",
    "ValuationClass": "ValuationClass", "AvailabilityCheckType": "AvailabilityCheckType",
    "PriceControl": "PriceControl",
}
# plant-specific values that are NOT in the codebook -> validated against the config-graph (B2).
_PLANT_SPECIFIC = {"StorageLocation": "storage_location", "MRPResponsible": "mrp_controller"}
# required coded fields: a header write missing one of these is blocked.
_REQUIRED = {"ProductType", "BaseUnit", "ProductGroup"}

_BOOK = None


def _book() -> dict:
    global _BOOK
    if _BOOK is None:
        for p in (_HERE / "code_book.json", _HERE / "mcp_server" / "code_book.json"):
            try:
                _BOOK = json.loads(p.read_text(encoding="utf-8"))
                break
            except (FileNotFoundError, ValueError):
                continue
        if _BOOK is None:
            _BOOK = {}
    return _BOOK


def _valid_codes(field: str):
    """The set of valid codes for a coded field from the codebook, or None if the field isn't in the
    codebook (unknown -> we can't validate it, so we never block on it)."""
    e = _book().get("by_odata_field", {}).get(field)
    if not e or not e.get("values"):
        return None
    return {v["code"] for v in e["values"]}


def _policy() -> dict:
    try:
        return json.loads(_POLICY.read_text(encoding="utf-8")).get("coded_grounding", {})
    except (FileNotFoundError, ValueError):
        return {}


def _collect(node, out: dict):
    """Collect {field: value} for coded + plant-specific fields ANYWHERE in the nested deep-insert."""
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, (dict, list)):
                _collect(v, out)
            elif (k in _CODED or k in _PLANT_SPECIFIC or k == "Plant") and str(v).strip():
                out.setdefault(k, str(v).strip())
    elif isinstance(node, list):
        for v in node:
            _collect(v, out)


def validate_grounding(payload, plant: str = None, require: bool = True) -> list[str]:
    """Return BLOCKING problems for a proposed payload ([] = grounded ok):
      * a required coded field missing (only when require=True -- a full create, not a partial patch),
      * a coded field whose value isn't a valid codebook code,
      * a plant-specific value (storage location, MRP controller) not valid for the plant.
    Unknown fields (not in the codebook) are never blocked -- we only block what we can verify."""
    fields = {}
    _collect(payload if isinstance(payload, (dict, list)) else {}, fields)
    plant = plant or fields.get("Plant")
    probs = []

    if require:
        for req in sorted(_REQUIRED):
            if not fields.get(req):
                probs.append(f"required coded field {req} is missing")

    for f in _CODED:
        val = fields.get(f)
        if not val:
            continue
        valid = _valid_codes(_CODED[f])
        if valid is not None and val not in valid:
            probs.append(f"{f}='{val}' is not a valid codebook value "
                         f"(use list_allowed_values('{_CODED[f]}'))")

    if plant:
        try:
            from config_graph import get_relation
            for f, rel in _PLANT_SPECIFIC.items():
                val = fields.get(f)
                if not val:
                    continue
                codes = [v["code"] for v in get_relation(rel, plant).get("values", [])]
                if codes and val not in codes:       # only block when the valid set is READABLE and excludes it;
                    probs.append(                    # if config-graph can't read it (no RFC/SDK), never false-block
                        f"{f}='{val}' is not valid for plant {plant} "
                        f"(use get_valid_{'storage_locations' if rel == 'storage_location' else 'mrp_controllers'})")
        except (Exception, SystemExit):
            pass            # config-graph unreachable (no RFC / SDK) -> skip plant-specific, never false-block
    return probs


def enforce(payload, plant: str = None, require: bool = True) -> str | None:
    """The write-path gate. Returns a BLOCK message if grounding fails and the policy enforces it,
    else None (write may proceed). Severity/active from policies.json -> coded_grounding."""
    pol = _policy()
    if not pol.get("enforce", True):
        return None
    probs = validate_grounding(payload, plant, require=require)
    if not probs:
        return None
    sev = pol.get("severity", "error")
    head = ("BLOCKED -- coded fields not grounded (codebook-grounding). Fix these, then retry:"
            if sev in ("error", "block") else "WARNING -- coded fields not grounded:")
    return head + "\n  - " + "\n  - ".join(probs)
