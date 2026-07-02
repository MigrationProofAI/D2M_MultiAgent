"""config_graph.py -- plant-keyed CONFIG (storage locations, MRP controllers) the value codebook can't
hold, read the SAME way the rest of the rig talks to SAP: OData-over-HTTPS via sap.py.

code_book.json grounds flat OData CODED domains (ProductType, MRPType, ...). But some valid values are
PLANT-SPECIFIC config, not flat domains, so the agent must NOT guess them:
  * storage locations for a plant  (classic T001L)
  * MRP controllers for a plant     (classic T024D)

CONNECTION -- we reuse sap._sap_get, the EXACT OData-over-HTTPS path the working genesis writes use
(basic auth + sap-client + the appliance session). NO pyrfc / RFC dependency: importing pyrfc hard-
exits (SystemExit) when the SDK is absent -- that crashed genesis -- and RFC won't traverse a BTP
destination. Because we ride on sap.py's session, config-graph AUTOMATICALLY follows whatever
connection sap.py uses: local appliance now, destination-through-Cloud-Connector under BTP, no change
here. The public tools (get_valid_storage_locations / get_valid_mrp_controllers) are the stable,
swappable contract; only the read implementation behind them changes.

SOURCE -- the dedicated master CDS views (I_StorageLocation, I_MRPController) are 403 / not exposed on
this appliance, so we read the values IN USE at the plant from the material domain that IS exposed:
  * storage_location <- distinct A_ProductStorageLocation.StorageLocation for the plant
  * mrp_controller   <- distinct A_ProductPlant.MRPResponsible for the plant
That is the set actually configured-and-used at the plant -- the realistic set to ground against (and
it makes the natural default the real in-use controller, e.g. 001, not a dummy master entry). If the
FULL config master is ever genuinely needed, add an RFC-via-ctypes provider (NOT pyrfc) behind
_read_relation -- without touching the tool contract.

Cached per (relationship, plant) per session; refresh_relationship() re-reads on demand. A read failure
degrades to a logged warning + an empty set -- it NEVER raises into genesis.
"""
import json
import logging

_log = logging.getLogger("config_graph")

# relationship -> the OData entity (under API_PRODUCT_SRV, read via sap._sap_get) + the field whose
# DISTINCT values are the plant's valid set. These entities don't carry the code's name (cosmetic only).
_RELATIONS = {
    "storage_location": {"path": "/sap/opu/odata/sap/API_PRODUCT_SRV/A_ProductStorageLocation",
                         "code": "StorageLocation", "label": "storage locations"},
    "mrp_controller":   {"path": "/sap/opu/odata/sap/API_PRODUCT_SRV/A_ProductPlant",
                         "code": "MRPResponsible", "label": "MRP controllers"},
}
_READ_TOP = "1000"          # rows scanned for distinct in-use values (cached per plant -> read once)

_CACHE: dict[tuple[str, str], list[dict]] = {}             # (relationship, plant) -> [{code, text}, ...]


def _read_relation(rel: str, plant: str) -> list[dict]:
    """DISTINCT in-use values for a plant. SAP_VIA_MCP on -> the cloud mcp-config-graph (no in-process
    OData); off -> sap._sap_get (the rig's working OData path). Raises on a transport/parse failure so
    get_relation can degrade + log (never crashes the caller)."""
    r = _RELATIONS[rel]
    # ---- cloud path: mcp-config-graph (same {values:[{code,text}]} shape this function returns) ----
    try:
        import mcp_route as _mr                   # lazy: same dir as sap on the rig's path
        via = _mr.VIA_MCP
    except Exception:
        _mr, via = None, False
    if via:
        tool = "get_valid_storage_locations" if rel == "storage_location" else "get_valid_mrp_controllers"
        txt = _mr.call("config", tool, {"plant": str(plant)})
        try:
            vals = json.loads(txt).get("values", [])
        except Exception:
            raise RuntimeError(txt)               # cloud error/non-JSON -> get_relation logs + degrades
        out, seen = [], set()
        for v in vals:
            c = str(v.get("code") or "").strip()
            if c and c not in seen:
                seen.add(c)
                out.append({"code": c, "text": v.get("text") or ""})
        return sorted(out, key=lambda v: v["code"])
    # ---- in-process OData (flag off) ----
    import sap                                    # lazy: the OData-over-HTTPS seam (same as the writes)
    raw = sap._sap_get(r["path"], {"$filter": f"Plant eq '{plant}'", "$select": r["code"], "$top": _READ_TOP})
    if not isinstance(raw, str) or raw.startswith("SAP request failed"):
        raise RuntimeError(raw if isinstance(raw, str) else "no response")
    rows = json.loads(raw).get("d", {}).get("results", [])
    out, seen = [], set()
    for x in rows:
        c = (x.get(r["code"]) or "").strip()
        if c and c not in seen:
            seen.add(c)
            out.append({"code": c, "text": ""})
    return sorted(out, key=lambda v: v["code"])


def get_relation(rel: str, plant: str) -> dict:
    """Cached valid {code,text} list for a plant-keyed relationship, read via OData once per (rel, plant).
    On failure: a logged warning + {"values": [], "error": ...} -- NEVER raises (genesis must not crash)."""
    if rel not in _RELATIONS:
        return {"error": f"unknown relationship '{rel}'. Known: {list(_RELATIONS)}", "values": []}
    plant = str(plant).strip()
    key = (rel, plant)
    if key not in _CACHE:
        try:
            _CACHE[key] = _read_relation(rel, plant)
        except Exception as e:                    # transport / parse / anything -> degrade, don't crash
            msg = (f"could not read {_RELATIONS[rel]['label']} for plant {plant} via OData "
                   f"({type(e).__name__}: {e})")
            _log.warning("config-graph: %s -- skipping plant-specific validation for this read", msg)
            return {"plant": plant, "relationship": rel, "label": _RELATIONS[rel]["label"],
                    "values": [], "error": msg}
    return {"plant": plant, "relationship": rel, "label": _RELATIONS[rel]["label"],
            "source": "odata: in use at plant", "values": _CACHE[key]}


def is_valid(rel: str, plant: str, code: str) -> bool:
    """True if `code` is in the plant's valid (in-use) set. False if absent OR the read failed -- callers
    that must not false-block on a read failure should check get_relation(...)['values'] is non-empty."""
    return any(v["code"] == str(code).strip() for v in get_relation(rel, plant).get("values", []))


def prefetch_plant(plant: str) -> dict:
    """Read ALL plant-keyed relationships for a plant once (e.g. at extension start), so later grounding
    is served from cache -- never a per-material round trip."""
    return {rel: len(get_relation(rel, plant).get("values", [])) for rel in _RELATIONS}


_NONPLANNING_MRP = {"", "ND", "X0"}      # no-planning MRP types -> no MRP controller required


def validate_plant_config(plant: str, storage_location: str = None, mrp_controller: str = None,
                          mrp_type: str = None) -> list[str]:
    """Deterministic backstop (assurance): a proposed plant-specific value not in the plant's valid set
    is BLOCKED before it reaches SAP. Returns blocking problems ([] = ok). A planning MRP type (not
    ND/blank) REQUIRES an MRP controller. CRUCIAL: only block a value when the set is actually READABLE
    -- if the OData read failed (empty + error), SKIP, never false-block."""
    probs = []

    def _check(rel: str, val: str, label: str):
        if not val:
            return
        codes = [v["code"] for v in get_relation(rel, plant).get("values", [])]
        if codes and str(val).strip() not in codes:       # readable AND excluded -> block; else skip
            probs.append(f"{label} '{val}' is not in use at plant {plant} "
                         f"(via OData; e.g. {codes[:12]})")

    _check("storage_location", storage_location, "storage location")
    if (mrp_type or "").strip().upper() not in _NONPLANNING_MRP and not mrp_controller:
        probs.append(f"MRP type '{mrp_type}' is a planning type but NO MRP controller was given -- "
                     f"SAP requires one for plant {plant}'s plant view (get_valid_mrp_controllers)")
    _check("mrp_controller", mrp_controller, "MRP controller")
    return probs


# ---- agent tools (registered in tools.py) -- STABLE contract; implementation above is swappable ----
def get_valid_storage_locations(plant: str) -> str:
    """List the storage locations IN USE at a plant (read live via OData, same path as the writes).
    Storage locations are plant-specific and NOT in the value codebook -- ground one from THIS list;
    never guess or reuse another plant's. Cached per plant."""
    return json.dumps(get_relation("storage_location", plant), indent=2)


def get_valid_mrp_controllers(plant: str) -> str:
    """List the MRP controllers IN USE at a plant (read live via OData). A planning MRP type (e.g. PD)
    REQUIRES an MRP controller; ground it from THIS list -- never guess or omit it. Cached per plant."""
    return json.dumps(get_relation("mrp_controller", plant), indent=2)


def refresh_relationship(relationship: str, plant: str) -> str:
    """Clear the cache for a plant-keyed relationship and RE-READ it from SAP (use after a config
    change). relationship: 'storage_location' | 'mrp_controller'."""
    _CACHE.pop((relationship, str(plant).strip()), None)
    return json.dumps(get_relation(relationship, plant), indent=2)
