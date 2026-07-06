"""mcp_server/genesis.py -- the multimodal GENESIS orchestrator.

Given a structured genesis spec (parent assembly + components + routing) -- produced from
an IMAGE + a CSV by the vision agent -- create the whole master-data set in SAP, in order:

    parent FERT (born routable)
      -> component materials (bought=HAWA/ROH, made=HALB/FERT)
      -> PIR + cost  (for each BOUGHT component)
      -> BOM   (parent + components)
      -> routing (parent)

DESIGN: the LLM does PERCEPTION (image -> spec); THIS does EXECUTION (spec -> SAP),
deterministically, so the long multi-write chain can't be fumbled by a cheap model.
Confirm-gated: confirm=false PREVIEWS the plan; confirm=true creates.

Standalone:  python ./mcp_server/genesis.py    (ADK launches it over stdio)
"""
import os
import sys
import csv
import json
import re
import asyncio
import threading
import collections

sys.path.insert(0, os.path.dirname(__file__))
from sap import (build_material_payload, create_material, get_material,  # noqa: E402
                 extend_to_plant, change_material_view)
from make import (create_info_record, create_cost_condition,           # noqa: E402
                  create_bom, create_routing)
from discipline import Spine                                           # noqa: E402  (S0-S8 spine)
from mcp.server.fastmcp import FastMCP                                  # noqa: E402
from mcp import ClientSession                                          # noqa: E402  (MCP CLIENT ->
from mcp.client.sse import sse_client                                  # noqa: E402   remote :8002 prodver)

mcp = FastMCP("genesis")
_DEF_PLANT = os.getenv("SAP_PLANT", "1710")
# The production version (MKAL) lives on YOUR remote RFC MCP server -- the ADK app holds no SAP SDK,
# so genesis reaches it the same way the agents do: over MCP. URL matches main.py's PRODVER_MCP_URL.
PRODVER_MCP_URL = os.getenv("PRODVER_MCP_URL", "http://127.0.0.1:8002/sse")
# SAP_VIA_MCP on -> route the WHOLE genesis chain through the cloud fleet: rebind the in-process SAP
# writers (sap.py/make.py) to signature-matched cloud shims, and use the CF prod-version route (retires
# local :8002). Explicit PRODVER_MCP_URL env still wins. Flag OFF -> nothing here changes (demo-safe).
try:
    import mcp_route as _mr  # noqa: E402
    if _mr.VIA_MCP:
        if not os.getenv("PRODVER_MCP_URL"):
            PRODVER_MCP_URL = _mr.SERVERS["prodver"][0]
        get_material = _mr.s_get_material
        create_material = _mr.s_create_material
        extend_to_plant = _mr.s_extend_to_plant
        change_material_view = _mr.s_change_material_view
        create_info_record = _mr.s_create_info_record
        create_cost_condition = _mr.s_create_cost_condition
        create_bom = _mr.s_create_bom
        create_routing = _mr.s_create_routing
except Exception:
    pass
# FALLBACK routing used ONLY when the spec/BOM supplies no operations (e.g. image genesis, or a file with no
# Operations sheet). Was a fake-looking 2-step Final Assembly -> Packaging that made every routing read as a
# real process; now ONE operation, its text marking it plainly as a placeholder to define -- the honest
# equivalent of net_price 0.01. A BOM Operations sheet supplies real, varied routings and overrides this.
_DEF_ROUTING = [{"operation": "0010", "text": "MAKE (default routing — no operations specified; define them)",
                 "work_center": "ASSEMBLY"}]


# ---- helpers ----------------------------------------------------------------
def _exists(matnr) -> bool:
    return bool(matnr) and '"Product"' in get_material(str(matnr))


def _readback(matnr):
    """S3 verification: re-read a just-touched material from SAP. Returns its 'd' dict (the
    grounding fact for S1/S2/S4) or None if the read-back fails -- which is itself a finding."""
    try:
        d = json.loads(get_material(str(matnr)))
        return d.get("d") if isinstance(d, dict) else None
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def _new_matnr(res: str) -> str | None:
    # SAP's 201 create response returns the new key several ways: as a "Product":"12449" field
    # (sometimes serialized with whitespace after the colon) OR only inside __metadata as
    # A_Product('12449'). The old regex matched only the tight no-space field form, so a whitespace
    # or metadata-only response made this return None -> genesis FALSELY aborted a parent it had just
    # created (HTTP 201), spawning duplicate FERTs and a dedup-reuse cascade. Tolerate both shapes.
    m = re.search(r'"Product"\s*:\s*"(\w+)"', res)
    if not m:
        m = re.search(r"A_Product\('(\w+)'\)", res)
    return m.group(1) if m else None


def _dossier(d: dict) -> str:
    """Render the 🛡 DISCIPLINE dossier (S0-S8) as an appended section: a human headline +
    the full structured record, so the agent AND the Activity panel can both read it."""
    head = (f"\n\n===== 🛡 DISCIPLINE DOSSIER (S0-S8) =====\n"
            f"verdict: {d['verdict']}   overall confidence: {d['overall_confidence']}   "
            f"cost: {d['cost']['writes']} writes / {d['cost']['wall_ms']} ms   "
            f"KG: +{d['kg_written']['nodes']} nodes / +{d['kg_written']['edges']} edges")
    for e in d["escalations"]:
        detail = e.get("why") or e.get("fact") or ""
        head += f"\n  ⚠ S7 ESCALATE {e['stage']}: {e['reason']}" + (f" ({detail})" if detail else "")
    # The agent needs the verdict/confidence/escalations/cost ABOVE + a one-line decisions roll-up; it
    # does NOT need the full structured record inline. The old `\`\`\`json {slim}\`\`\`` block was ~11k chars
    # (decisions + a duplicate of the escalations already in the head + reopen_plan) and piled up in the
    # model context across turns. The full detail lives durably in the sidecars (kg_instances.json +
    # genesis_ledger.json) and travels to the UI via the @@DATA@@ card -- so it is NOT lost here.
    decisions = d.get("decisions") or []
    if decisions:
        head += "\n  decisions: " + "; ".join(
            f"{x.get('stage', '?')}={x.get('decision') or x.get('outcome') or x.get('result') or '?'}"
            if isinstance(x, dict) else str(x) for x in decisions)[:600]
    return head


def _discipline_summary(d: dict) -> dict:
    """The S0-S8 roll-up compacted for the structured card (verdict / confidence / escalations)."""
    return {"verdict": d.get("verdict"), "confidence": d.get("overall_confidence"),
            "writes": (d.get("cost") or {}).get("writes"),
            "escalations": [{"stage": e.get("stage"), "reason": e.get("reason"),
                             "detail": e.get("why") or e.get("fact") or ""}
                            for e in d.get("escalations", [])]}


def _run_async(make_coro):
    """Run a coroutine to completion from inside a SYNC FastMCP tool. The tool body executes IN the
    server's running event loop, so asyncio.run() here would raise -- run it in a private thread with
    its own loop instead. Re-raises any failure to the caller."""
    box = {}

    def worker():
        try:
            box["v"] = asyncio.run(make_coro())
        except BaseException as e:                  # noqa: BLE001 -- surface to the caller thread
            box["e"] = e

    th = threading.Thread(target=worker, daemon=True)
    th.start()
    th.join()
    if "e" in box:
        raise box["e"]
    return box["v"]


# Lot size on the MKAL: BSTMI = minimum, BSTMA = maximum (the :8002 tool takes them via extra_fields).
# Hard-coded 1..10000 for the demo; parameterize via the spec later.
_LOT_SIZE = {"BSTMI": "1", "BSTMA": "10000"}


def _note_mcp(url):                                  # TELEMETRY: count a prodver cloud call under its server
    try:
        import re
        import mcp_route as _mr
        m = re.match(r"https?://([^./]+)", url)
        _mr._note_call(m.group(1) if m else url)
    except Exception:
        pass


def _create_production_version(material, plant, desc):
    """Create the PRODUCTION VERSION via the mcp-routing MCP CONTRACT (OData MPE_MANAGE_PRODVER_SRV):
    binds the BOM (usage 1 / alternative 1) + lot size 1..10000 so MRP can plan it (clears MD408).
    Returns (ok: bool, message: str); never raises.

    This REPLACES the retired RFC create on sap-prodvers-mcp -- PV writes now go through the SAME OData
    contract as PV reads (get_routing / read_production_version / create_production_version all on
    mcp-routing). See [[mcp-tool-contract]] + [[prodver-odata-crud]]."""
    import mcp_route
    args = {"material": str(material), "plant": str(plant), "production_version": "0001",
            "bom_alternative": "1", "bom_usage": "1",
            "min_lot": _LOT_SIZE["BSTMI"], "max_lot": _LOT_SIZE["BSTMA"],
            "text": f"{(desc or str(material))[:28]} version 1", "confirm": True}
    try:
        txt = mcp_route.call("routing", "create_production_version", args)
    except Exception as e:
        return False, f"mcp-routing prodver create unreachable/failed -- {type(e).__name__}: {e}"
    # Success covers BOTH the fixed tool's outputs: "CREATED + VERIFIED production version ..." and the
    # idempotent "... already exists (verified by read-back)". Match on VERIFIED/exists, not the old exact
    # "CREATED production version" string (the tool's "+ VERIFIED" broke that substring -> false NOT-bound).
    low = (txt or "").lower()
    ok = ("verified production version" in low or "already exists" in low) and "fail" not in low
    return ok, (txt or "(no text)")


# RETIRED: the RFC prodver bridge (_call_prodver -> sap-prodvers-mcp/:8002) is gone. Production version
# create AND read now go through the mcp-routing OData contract (create_production_version /
# read_production_version -> MPE_MANAGE_PRODVER_SRV). PRODVER_MCP_URL above is kept only as a dormant
# config stub and is no longer called. See [[mcp-tool-contract]] + [[prodver-odata-crud]].


# DESIGN PRINCIPLE: routing + production version are OData objects OWNED by the mcp-routing MCP server.
# Every object's reads AND writes go through its MCP tool contract (which must expose full CRUD) -- the
# rig NEVER bypasses the contract with a direct in-process OData call. So these read-backs route to
# mcp-routing. (Only the PV *create* is RFC on sap-prodvers-mcp; its read-back lives on mcp-routing.)
def _routing_read(remote_tool: str, material: str, plant: str) -> str:
    """Call the mcp-routing MCP server (via mcp_route) with ONE retry on a transient CF->SAP auth
    hiccup ('Logon failed' / 401). Returns the raw tool text; callers shape it into a lean, HONEST
    presence signature -- an unreadable result is reported as an error, never as present or absent.
    (Final server-side minimization is the mcp-routing lens's job -- this rig-side shaping is the
    interim bridge until that lands.)"""
    import mcp_route
    args = {"material": str(material), "plant": str(plant)}
    out = mcp_route.call("routing", remote_tool, args)
    if "Logon failed" in (out or "") or (out or "")[:40].find("401") >= 0:
        out = mcp_route.call("routing", remote_tool, args)          # transient hiccup -> retry once
    return out


def read_production_version(material: str, plant: str = "1710") -> str:
    """READ the production version(s) for a MADE material (FERT/HALB) via the mcp-routing MCP server
    (read_production_version -> I_ProductionVersionStdVH). LEAN signature: {"versions":["0001"]} when
    bound; {"versions":[],"note":"no production version -- a gap"} when none. (PV *create* is RFC on
    sap-prodvers-mcp; this is the verify read-back, through the routing contract.)"""
    return _routing_read("read_production_version", material, plant)


def read_routing(material: str, plant: str = "1710") -> str:
    """READ the routing assignment(s) for a MADE material via the mcp-routing MCP server (get_routing ->
    ProductionRoutingMatlAssgmt). LEAN, HONEST signature: {"present":true,"routings":[{group,counter}]}
    when a routing exists; {"present":false,...,"note":"no routing -- a gap"} when none;
    {"present":null,"error":...} when the READ itself failed -- an error is NEVER dressed up as present
    or absent."""
    raw = _routing_read("get_routing", material, plant)
    try:
        rows = json.loads(raw).get("d", {}).get("results", [])
    except Exception:
        return json.dumps({"material": str(material), "plant": str(plant), "present": None,
                           "error": (raw or "")[:160]})
    groups = [{"group": r.get("ProductionRoutingGroup"),
               "counter": r.get("ProductionRouting") or r.get("ProductionRtgMatlAssgmtIntVers")}
              for r in rows if isinstance(r, dict) and r.get("ProductionRoutingGroup")]
    if not groups:
        return json.dumps({"material": str(material), "plant": str(plant),
                           "present": False, "routings": [], "note": "no routing -- a gap"})
    return json.dumps({"material": str(material), "plant": str(plant), "present": True, "routings": groups})


def _create_material(spec: dict, plant: str) -> tuple[str | None, str]:
    """Create one material (parent or component) via the verified payload builder.
    FERT parents are born routable (procurement E + work-scheduling) and get a sales view.

    A spec node MAY carry explicit SAP classification -- product_group, valuation_class,
    procurement_type, mrp_type, unit -- which are threaded to build_material_payload's existing
    params so a source of record (e.g. a CAD part master, a BOM file) sets the REAL codes instead
    of D2M's type-derived defaults. These are VIEW fields (plant/valuation) the attributes header
    passthrough can't reach, so this is their only channel. Absent keys -> the defaults are
    unchanged, so every existing spec builds byte-identically."""
    ptype = spec.get("type", "HAWA")
    _opt = {}
    if spec.get("product_group"):
        _opt["product_group"] = str(spec["product_group"])
    if spec.get("valuation_class"):
        _opt["valuation_class"] = str(spec["valuation_class"])
    if spec.get("procurement_type"):
        _opt["procurement_type"] = str(spec["procurement_type"])
    if spec.get("mrp_type"):
        _opt["mrp_type"] = str(spec["mrp_type"])
    if spec.get("unit"):
        _opt["base_unit"] = str(spec["unit"])
    built = json.loads(build_material_payload(
        description=(spec.get("description") or spec.get("name") or "Material")[:40],
        product_type=ptype, plant=plant,
        sales_org="1710" if ptype == "FERT" else None,
        extra_fields=spec.get("attributes"),        # $metadata-validated passthrough: weights, dims, etc.
        **_opt,                                      # explicit SAP classification when the spec carries it
    ))
    payload, notes = built["fields"], built.get("extra_notes") or []
    res = create_material(fields=payload, confirm=True)
    mat = _new_matnr(res)
    # RESILIENCE: an OPTIONAL engineering attribute must never cost us the material. If the deep-insert
    # was rejected (no matnr) AND we sent passthrough attributes, retry ONCE with a clean base payload
    # (no extra_fields) so the material is still created -- and say which attributes were dropped. The
    # passthrough's contract is "a bad attribute is skipped, never breaks the create"; this makes that
    # hold for a bad VALUE (e.g. a unit SAP won't accept), not just a bad field name.
    if not mat and spec.get("attributes"):
        base = json.loads(build_material_payload(
            description=(spec.get("description") or spec.get("name") or "Material")[:40],
            product_type=ptype, plant=plant,
            sales_org="1710" if ptype == "FERT" else None, **_opt))   # NO extra_fields this time
        res2 = create_material(fields=base["fields"], confirm=True)
        mat = _new_matnr(res2)
        if mat:
            res = f"{res2}  [attrs DROPPED after create was rejected with them: {list(spec['attributes'].keys())}]"
            return mat, res
    if notes:                                        # surface which extra fields were set / skipped
        res = f"{res}  [attrs: {'; '.join(notes)}]"
    return mat, res


# ---- semantic DEDUP at the very start (scoped) + write-back -----------------
# Reuse the vector engine's pure functions IN-PROCESS so genesis can ask "does this already exist?"
# BEFORE it creates, and write each new material back into the index so the NEXT run sees it.
try:
    from vector import _search as _vec_search, _add_material as _vec_add, _DUP_THRESHOLD as _VEC_THR
    _DEDUP_OK = True
except Exception as _e:                                  # faiss/openai missing -> degrade gracefully
    _DEDUP_OK = False
    _VEC_THR = 0.92
    def _vec_search(*a, **k): return []
    def _vec_add(*a, **k): return (False, "vector engine unavailable")

_DEDUP_FROM = os.getenv("DEDUP_FROM", "")                 # SAP-style range to scope dedup within
_DEDUP_TO = os.getenv("DEDUP_TO", "")
_DEDUP_THR = float(os.getenv("DEDUP_THRESHOLD", "0.96"))   # cosine >= this => auto-reuse. Raised from
# 0.92: at 0.92 distinct parts whose generic role embeds alike (cable / USB board / audio board; L/R
# fan) over-collapsed onto ONE material. 0.96 keeps true-dup reuse but separates near-but-distinct parts.
# Dedup default for this testing rig is OFF -- every genesis run CREATES fresh (no semantic reuse), so a
# from-scratch test never silently reuses an old material no matter how the rig was launched. Set
# GENESIS_DEDUP=on (or true/1/yes) to turn dedup back ON globally; a single run can still override either
# way via spec {"dedup": true|false}.
_DEDUP_DEFAULT = os.getenv("GENESIS_DEDUP", "off").strip().lower() not in ("off", "false", "0", "no")
_DATA = "@@DATA@@"                                        # sentinel: <readable text>@@DATA@@<json>


def _dedup(description: str, lo: str = "", hi: str = "") -> dict:
    """Closest EXISTING material to `description` (scoped to [lo, hi]) with a confidence score and a
    verdict. is_duplicate => we should reuse it instead of minting a near-identical twin."""
    desc = (description or "").strip()
    if not _DEDUP_OK or not desc:
        return {"checked": False, "is_duplicate": False, "threshold": _DEDUP_THR, "match": None, "candidates": []}
    cands = _vec_search(desc, 5, lo or _DEDUP_FROM, hi or _DEDUP_TO)
    best = cands[0] if cands else None
    is_dup = bool(best and best["score"] >= _DEDUP_THR)
    return {"checked": True, "is_duplicate": is_dup, "threshold": round(_DEDUP_THR, 3),
            "match": best if is_dup else None, "candidates": cands}


def _emit(text: str, data: dict) -> str:
    """Return the human report with a machine-readable structured payload appended after a sentinel.
    main.py strips everything from the sentinel on for chat/activity, and parses the JSON for the
    Data panel -- so the same call drives a readable dossier AND a typed card."""
    try:
        return text + "\n" + _DATA + json.dumps(data, ensure_ascii=False, default=str)
    except Exception:
        return text


def _plain(s: str) -> str:
    """Strip a make-tool's @@DATA@@ card block: genesis builds its own roll-up payload, so it only
    wants the readable text for its report + discipline records."""
    return s.split(_DATA, 1)[0].rstrip() if isinstance(s, str) and _DATA in s else s


def genesis_from_csv(path: str) -> dict:
    """Load a genesis spec from a CSV (the 'something else' that complements the image).
    Columns: role(parent|bought|made), name, material, description, type, vendor, price,
    quantity, unit. One parent row + N component rows."""
    parent, comps = {}, []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            role = (r.get("role") or "").strip().lower()
            row = {"name": r.get("name", "").strip(),
                   "material": (r.get("material") or "").strip() or None,
                   "description": r.get("description", "").strip(),
                   "type": (r.get("type") or "HAWA").strip(),
                   "vendor": (r.get("vendor") or "").strip() or None,
                   "price": float(r["price"]) if r.get("price") else None,
                   "quantity": float(r["quantity"]) if r.get("quantity") else 1,
                   "unit": (r.get("unit") or "EA").strip()}
            if role == "parent":
                parent = {"description": row["description"] or row["name"],
                          "type": row["type"], "plant": _DEF_PLANT,
                          "material": row["material"]}
            else:
                row["role"] = "made" if role == "made" else "bought"
                comps.append(row)
    return {"parent": parent, "components": comps}


@mcp.tool()
def _norm_name(s: str) -> str:
    """Normalise a part description for shared-raw dedup within ONE genesis run."""
    return " ".join((s or "").lower().split())


def _build_made_subassembly(c: dict, plant: str, sp, report: list, created_raws: dict, _dd) -> dict | None:
    """Build ONE made (HALB) component's OWN sub-structure: its raw children (deduped across the run so a
    shared raw like epoxy/bolts is created once), its BOM (HALB + children), routing, and production
    version. `c` must carry c['material'] (created in the component pass) and c['components'] (sub-parts).
    This is what makes genesis MULTI-LEVEL: every made node, not just the FERT, gets BOM+routing+PV."""
    halb = c.get("material")
    children = c.get("components") or []
    if not halb or not children:
        return None
    sub = {"material": halb, "name": c.get("name"), "description": c.get("description"),
           "children": [], "bom": None, "routing": None, "production_version": None}
    child_rows = []
    for ch in children:
        cmat = ch.get("material")
        cdesc = ch.get("description") or ch.get("name") or ""
        if not _exists(cmat):
            key = _norm_name(cdesc)
            if key in created_raws:                       # shared raw already made this run -> reuse
                cmat = created_raws[key]
                report.append(f"      raw {ch.get('name')}: reuse {cmat} (shared)")
            else:
                cdd = _dd(cdesc)
                if cdd["is_duplicate"]:
                    cmat = cdd["match"]["Product"]
                    report.append(f"      raw {ch.get('name')}: reused {cmat} (semantic dup)")
                else:
                    cmat, res = _create_material(ch, plant)
                    if not cmat:
                        report.append(f"      raw {ch.get('name')}: CREATE FAILED {res[:80]}")
                        sp.record(f"raw:{ch.get('name')}", "create raw", "failed", outcome=res[:80])
                        continue
                    report.append(f"      raw {ch.get('name')}: created {cmat} [{ch.get('type', 'ROH')}]")
                    sp.record(f"raw:{ch.get('name')}", "create raw", "created", outcome=f"created {cmat}",
                              obj=_readback(cmat), writes=1, inputs={"desc": cdesc, "type": ch.get("type", "ROH")})
                    _vec_add(cmat, cdesc[:60])
                created_raws[key] = cmat
            ch["material"] = cmat
        else:
            report.append(f"      raw {ch.get('name')}: exists {cmat}")
        # MULTI-LEVEL RECURSION: if this child is itself a MADE sub-assembly (a HALB with its OWN
        # components), build ITS full sub-structure the same way -- own BOM + routing + production
        # version -- to ANY depth (FERT->HALB->HALB->...). Written ONCE here: depth is now purely a
        # data question. The child is then a MADE component of this HALB's BOM (no PIR/cost -- made,
        # not bought). Terminates naturally: a child with no components / all-bought children stops.
        if cmat and ch.get("components") and (ch.get("role") == "made" or ch.get("type") in ("HALB", "FERT")):
            ch["material"] = cmat
            _deep = _build_made_subassembly(ch, plant, sp, report, created_raws, _dd)
            if _deep:
                sub.setdefault("subassemblies", []).append(_deep)
        # Source bought raws at THIS sub-assembly level too -- PIR + cost, mirroring the top-level
        # component block (~line 619). Closes the gap where a nested bought raw was created but never
        # sourced (no PIR/cost), so a multi-layer BOM is sourced everywhere a bought part sits.
        elif ch.get("role") == "bought" and ch.get("vendor") and cmat:
            _rp = float(ch["price"]) if ch.get("price") not in (None, "") else 0.01
            _rpir = _plain(create_info_record(cmat, ch["vendor"], net_price=_rp, confirm=True))
            report.append(f"      raw PIR {ch.get('name')}: {'ok' if 'Created' in _rpir else _rpir[:70]}")
            if ch.get("price"):
                _rcost = _plain(create_cost_condition(cmat, ch["vendor"], float(ch["price"]), confirm=True))
                report.append(f"      raw cost {ch.get('name')}: {'ok' if 'Created' in _rcost else _rcost[:70]}")
        child_rows.append({"component": cmat, "quantity": ch.get("quantity", 1)})
        sp.add_kg(cmat, ch.get("type", "ROH"), description=cdesc[:40])
        sp.add_kg(halb, "HALB", edges=[("uses", cmat, {"quantity": ch.get("quantity", 1)})])
        sub["children"].append({"name": ch.get("name"), "material": cmat,
                                "quantity": ch.get("quantity", 1), "type": ch.get("type")})
    # HALB BOM (HALB + its raws) -----------------------------------------------
    if child_rows:
        bom = _plain(create_bom(halb, plant, child_rows, confirm=True))
        bok = "created" in bom.lower() or "ok" in bom.lower()
        report.append(f"    HALB {halb} BOM: {bom[:100]}")
        sub["bom"] = {"status": "ok" if bok else "failed", "components": len(child_rows), "message": bom[:120]}
        sp.record(f"subbom:{halb}", "create HALB BOM", "created" if bok else "failed", outcome=bom[:120],
                  verified=bok, grounded_by=bom[:120], writes=1 if bok else 0,
                  inputs={"parent": halb, "components": child_rows})
    # HALB routing -------------------------------------------------------------
    rtops = c.get("routing") or _DEF_ROUTING
    rt = _plain(create_routing(halb, plant, rtops,
                description=f"{(c.get('description') or '')[:24]} routing", confirm=True))
    rok = "created" in rt.lower() or "ok" in rt.lower()
    report.append(f"    HALB {halb} routing: {rt[:90]}")
    sub["routing"] = {"status": "ok" if rok else "failed",
                      "operations": [{"operation": o.get("operation"), "text": o.get("text"),
                                      "work_center": o.get("work_center")} for o in rtops], "message": rt[:120]}
    sp.record(f"subrouting:{halb}", "create HALB routing", "created" if rok else "failed", outcome=rt[:120],
              verified=rok, grounded_by=rt[:120], writes=1 if rok else 0, inputs={"parent": halb, "ops": rtops})
    for o in rtops:
        sp.add_kg(o["work_center"], "work_center")
        sp.add_kg(halb, "HALB", edges=[("routed_thru", o["work_center"], {"op": o.get("operation")})])
    # HALB production version ---------------------------------------------------
    pv_ok, pv_msg = _create_production_version(halb, plant, c.get("description"))
    report.append(f"    HALB {halb} PV: {'ok' if pv_ok else 'NOT bound -- ' + pv_msg[:80]}")
    sub["production_version"] = {"status": "ok" if pv_ok else "failed", "version": "0001",
                                 "bom_alt": "01", "bom_usage": "1", "message": pv_msg[:120]}
    sp.record(f"subpv:{halb}", "create HALB production version", "created" if pv_ok else "failed",
              outcome=pv_msg[:120], verified=pv_ok, grounded_by=pv_msg[:120], writes=1 if pv_ok else 0,
              inputs={"parent": halb, "version": "0001", "bom_alt": "01", "bom_usage": "1"})
    sp.add_kg(f"PV-{halb}-0001", "production_version", bound_bom="alt 01 / usage 1")
    sp.add_kg(halb, "HALB", edges=[("has_production_version", f"PV-{halb}-0001", {})])
    return sub


def _preview_subtree(node, out, indent):
    """Render a made node's children in the PREVIEW tree, RECURSIVELY to ANY depth. A made child is
    noted as getting its OWN BOM/routing/PV, then its own sub-tree is rendered one level deeper --
    so a 3- or 7-level structure shows every sub-assembly, matching what run_genesis actually builds."""
    pad = "    " * indent
    for ch in node.get("components") or []:
        chex = _exists(ch.get("material"))
        ktag = f"exists {ch.get('material')}" if chex else "CREATE"
        deep = bool((ch.get("role") == "made" or ch.get("type") in ("HALB", "FERT")) and ch.get("components"))
        src = (f"  -> PIR+cost @ {ch.get('vendor')}/{ch.get('price')}"
               if ch.get("role") == "bought" and ch.get("vendor") else "")
        flag = " ⚠ inferred" if ch.get("inferred") else ""
        out.append(f"{pad}  └ {ch.get('name')}: [{ktag}] {ch.get('type', 'ROH')} x{ch.get('quantity', 1)}{src}{flag}")
        if deep:
            out.append(f"{pad}      ↳ own BOM + routing + production version (made sub-assembly)")
            _preview_subtree(ch, out, indent + 1)


def _reconcile_created(parent: dict | None, comps: list, pmat, has_parent: bool) -> dict:
    """B1 -- the maker reconciles its OWN create-loop before claiming done. Deterministic count of the
    spec nodes this run RECEIVED vs the nodes that ended the run with a material number (the loops write
    each created/reused number back into its node; a failed/skipped node stays bare). Any gap is a typed
    IncompleteCreation -- a partial create is an INCOMPLETE state, never a silent success. (This checks
    the spec run_genesis received; the Verifier's manifest reconciliation additionally catches a spec
    that arrived already truncated/flattened.)"""
    def _walk(nodes):
        for n in nodes or []:
            yield n
            yield from _walk(n.get("components"))
    planned_nodes = list(_walk(comps))
    missing = [str(n.get("name") or n.get("description") or "?")
               for n in planned_nodes if not n.get("material")]
    planned = len(planned_nodes) + (1 if has_parent else 0)
    if has_parent and not pmat:
        missing.insert(0, str((parent or {}).get("description") or "parent"))
    created = planned - len(missing)
    return {"kind": "IncompleteCreation" if missing else "reconciled",
            "planned": planned, "created": created, "missing": missing, "complete": not missing}


def _recon_lines(recon: dict) -> str:
    """Render the maker's self-reconciliation as report lines (INCOMPLETE names every missing node)."""
    if recon["complete"]:
        return f"\nRECONCILED: created {recon['created']}/{recon['planned']} planned materials ✓"
    lines = [f"\n⛔ INCOMPLETE CREATION: created {recon['created']}/{recon['planned']} planned materials — "
             f"{len(recon['missing'])} MISSING:"]
    lines += [f"  MISSING {m}" for m in recon["missing"]]
    lines.append("Do NOT treat this genesis as complete. The missing nodes were never created.")
    return "\n".join(lines)


class _EmitList(list):
    """A `report` list that STREAMS each line the instant it's appended -- turns the silent deterministic
    build into a LIVE per-object feed (material · PIR · cost · BOM · routing · PV) with no change to the ~900
    append sites (run_genesis + _build_made_subassembly share this one list). on_step is the run_turn-style
    callback; a hiccup in it must NEVER break the build."""
    def __init__(self, on_step=None):
        super().__init__()
        self._on = on_step

    def append(self, item):
        super().append(item)
        if self._on:
            try:
                self._on({"kind": "reasoning", "text": str(item)})
            except Exception:
                pass


def run_genesis(spec: dict, confirm: bool = False, on_step=None) -> str:
    """Create a whole assembly's master data from a genesis spec (the heart of Design2Make):
    parent FERT -> component materials -> PIR+cost (bought) -> BOM -> routing.

    on_step (optional): a run_turn-style callback -> each build step (material/PIR/cost/BOM/routing/PV)
    streams live as it happens, so a big deterministic commit isn't a silent multi-minute block.

    MULTI-LEVEL: a made (HALB) component may carry its OWN "components" (its raws/sub-parts) and
    "routing"; run_genesis then builds that sub-assembly's BOM + routing + production version too, so
    the whole tree is born MRP-ready in one pass (not just the FERT). A flat spec (no nested
    components) behaves exactly as before.

    SAFETY GATE: confirm=false (default) returns the PLAN (existence checks, what will be
    created) and writes NOTHING. confirm=true performs all creates in order and reports.

    spec = {
      "parent": {"description": str, "type": "FERT", "plant"?: "1710", "material"?: <existing>},
      "components": [{"name", "description", "type" (HAWA/ROH=bought, HALB/FERT=made),
                      "role": "bought"|"made", "vendor"?, "price"?, "quantity"?, "unit"?,
                      "material"?: <existing, or null to create new>}],
      "routing"?: [{"operation","text","work_center"}],  # defaults to Assembly + Packaging
      "dedup"?: bool       # default true; false = FORCE a fresh build (create everything new, no reuse)
    }
    """
    parent = spec.get("parent") or {}
    plant = parent.get("plant") or _DEF_PLANT
    comps = spec.get("components", [])
    routing = spec.get("routing") or _DEF_ROUTING
    lo, hi = spec.get("dedup_from", _DEDUP_FROM), spec.get("dedup_to", _DEDUP_TO)   # scope the dedup
    # GENESIS_DEDUP is the MASTER switch. When the rig is launched with it OFF, a genesis is ALWAYS a
    # fresh build -- the spec CANNOT re-enable reuse (the model often sets {"dedup": true} because the
    # tool doc used to say "default true", which silently reused day-old materials, e.g. a skateboard
    # reusing an old bicycle's wheels). Only when GENESIS_DEDUP is ON does the spec get to fine-tune.
    dedup_on = bool(_DEDUP_DEFAULT) and spec.get("dedup", True)

    def _dd(desc):
        """Dedup a description -- UNLESS this run turned dedup off, in which case every part is treated
        as new (a clean create path, e.g. for testing the create chain end to end)."""
        if not dedup_on:
            return {"checked": False, "is_duplicate": False, "threshold": _DEDUP_THR,
                    "match": None, "candidates": []}
        return _dedup(desc, lo, hi)
    # A spec with NO parent FERT is a COMPONENTS-ONLY run (e.g. "create DDR RAM + its PIR + cost"):
    # create the component(s) + PIR/cost, and SKIP BOM/routing/production-version. A bought part has
    # nothing to manufacture, so a production version is meaningless (and fails -- "material not valid").
    has_parent = bool(parent.get("material") or parent.get("description"))

    if not confirm:
        gres = {"kind": "genesis", "mode": "preview", "plant": plant, "parent": None,
                "components": [], "bom": None, "routing": None, "production_version": None, "discipline": None}
        out = ["GENESIS PREVIEW -- nothing written. Confirm to create the full set."]
        # ROLLUP across ALL levels -- so the WHOLE tree size is front-and-centre (e.g. "100 materials"),
        # not just the FERT's direct children. Walks nested sub-assembly raws too.
        def _walk(nodes):
            for c in nodes:
                yield c
                yield from _walk(c.get("components") or [])
        _all = list(_walk(comps))
        _types = collections.Counter((c.get("type") or "?").upper() for c in _all)
        if has_parent:
            _types[(parent.get("type") or "FERT").upper()] += 1
        _mat_total = sum(_types.values())
        _made_sets = (1 if has_parent else 0) + sum(1 for c in _all if c.get("role") == "made" and c.get("components"))
        _pir = sum(1 for c in _all if c.get("role") == "bought" and c.get("vendor"))
        _cost = sum(1 for c in _all if c.get("role") == "bought" and c.get("price") not in (None, ""))
        _order = ["FERT", "HALB", "HAWA", "ROH"]
        _parts = [f"{_types[t]} {t}" for t in _order if _types.get(t)]
        _parts += [f"{n} {t}" for t, n in _types.items() if t not in _order]
        out.append(f"\nROLLUP (all levels): {_mat_total} materials  =  " + "  +  ".join(_parts))
        out.append(f"  objects: {_made_sets} BOMs · {_made_sets} routings · {_made_sets} production versions"
                   f"  ·  {_pir} PIRs · {_cost} cost conditions (every bought part, every level)")
        if has_parent:
            pex = _exists(parent.get("material"))
            pdd = None if pex else _dd(parent.get("description"))
            paction = "exists" if pex else ("dedup-reuse" if (pdd and pdd["is_duplicate"]) else "create")
            pmatp = parent.get("material") if pex else (pdd["match"]["Product"] if paction == "dedup-reuse" else None)
            tag = (f"  [exists {pmatp}]" if pex else
                   (f"  [REUSE {pmatp} · ~{pdd['match']['score']} dup]" if paction == "dedup-reuse" else "  [CREATE]"))
            out.append(f"\nPARENT (FERT, born routable @ {plant}): {parent.get('description')}{tag}")
            gres["parent"] = {"description": parent.get("description"), "material": pmatp,
                              "type": parent.get("type", "FERT"), "action": paction, "dedup": pdd}
        else:
            out.append("\n(COMPONENTS-ONLY -- no parent assembly, so NO BOM / routing / production version)")
        out.append(f"\nCOMPONENTS ({len(comps)}):")
        for c in comps:
            cex = _exists(c.get("material"))
            cdd = None if cex else _dd(c.get("description") or c.get("name"))
            caction = "exists" if cex else ("dedup-reuse" if (cdd and cdd["is_duplicate"]) else "create")
            cmatp = c.get("material") if cex else (cdd["match"]["Product"] if caction == "dedup-reuse" else None)
            tag = (f"exists {cmatp}" if cex else
                   (f"REUSE {cmatp} ~{cdd['match']['score']}" if caction == "dedup-reuse" else "CREATE"))
            extra = (f"  -> PIR + cost @ vendor {c.get('vendor')} / {c.get('price')}"
                     if c.get("role") == "bought" and c.get("vendor") else "")
            dupnote = (f"  (closest {cdd['candidates'][0]['Product']} ~{cdd['candidates'][0]['score']})"
                       if caction == "create" and cdd and cdd["candidates"] else "")
            out.append(f"  - {c.get('name')}: [{tag}] {c.get('type')}/{c.get('role')} x{c.get('quantity')}{extra}{dupnote}")
            gres["components"].append(
                {"name": c.get("name"), "description": c.get("description") or c.get("name"),
                 "type": c.get("type"), "role": c.get("role"), "quantity": c.get("quantity", 1),
                 "material": cmatp, "action": caction, "vendor": c.get("vendor"), "price": c.get("price"),
                 "dedup": cdd})
            # MULTI-LEVEL preview: a MADE node carries its own sub-parts -> render the FULL sub-tree to
            # ANY depth, noting each made node gets its OWN BOM/routing/PV (infer flags preserved).
            if (c.get("role") == "made" or c.get("type") in ("HALB", "FERT")) and (c.get("components")):
                out.append("        -> gets its OWN BOM + routing + production version (made sub-assembly)")
                _preview_subtree(c, out, 1)
                gres["components"][-1]["subassembly"] = True
                gres["components"][-1]["children"] = [
                    {"name": ch.get("name"), "type": ch.get("type", "ROH"), "quantity": ch.get("quantity", 1),
                     "material": ch.get("material"), "action": "exists" if _exists(ch.get("material")) else "create",
                     "inferred": bool(ch.get("inferred"))} for ch in (c.get("components") or [])]

        def _all_made(cs):                                # every made node WITH children, at ANY depth
            acc = []
            for x in cs:
                if (x.get("role") == "made" or x.get("type") in ("HALB", "FERT")) and x.get("components"):
                    acc.append(x)
                    acc += _all_made(x.get("components"))
            return acc
        made_subs = _all_made(comps)
        if has_parent:
            tag = (f"  +{len(made_subs)} sub-assembly BOM/routing/production-version set(s)"
                   if made_subs else "")
            out.append(f"\nthen BOM (parent + {len(comps)} components){tag}"
                       f"  and ROUTING ({' -> '.join(o['work_center'] for o in routing)})")
            out.append("then PRODUCTION VERSION 0001 (bind BOM alt 01 / usage 1) "
                       "-> the assembly becomes MRP-ready (clears MD408).")
            if made_subs:
                out.append(f"FULL TREE: {len(made_subs)} made sub-assembly(ies) each get their OWN BOM + "
                           "routing + production version -> multi-level, born MRP-ready in ONE pass.")
        return _emit("\n".join(out), gres)

    report = _EmitList(on_step)                       # commit path: every appended line streams live
    sp = Spine("genesis", plant=plant)               # 🛡 S0-S8 spine wraps every stage below
    gres = {"kind": "genesis", "mode": "complete", "plant": plant, "parent": None,
            "components": [], "bom": None, "routing": None, "production_version": None, "discipline": None}

    # 1) PARENT (full-assembly runs only; a components-only run has no FERT) ---
    pmat = None
    if has_parent:
        pdesc = parent.get("description")
        pmat = parent.get("material")
        if _exists(pmat):
            report.append(f"parent exists: {pmat}")
            sp.material = pmat
            sp.record("parent", "reuse FERT", "exists", outcome=f"exists {pmat}", obj=_readback(pmat),
                      inputs={"desc": pdesc, "type": parent.get("type")},
                      decision={"choice": f"reuse existing {pmat}", "because": "material already in SAP",
                                "alternatives": ["create a new FERT"]})
            paction, pdd = "exists", None
        else:
            pdd = _dd(pdesc)                         # <-- dedup BEFORE create (skipped if dedup off)
            if pdd["is_duplicate"]:
                pmat = pdd["match"]["Product"]
                report.append(f"parent: reused {pmat} (semantic dup ~{pdd['match']['score']} of '{pdesc}')")
                sp.material = pmat
                sp.record("parent", "dedup-reuse FERT", "exists",
                          outcome=f"reused {pmat} (score {pdd['match']['score']})", obj=_readback(pmat),
                          inputs={"desc": pdesc}, decision={"choice": f"reuse {pmat} (semantic match)",
                          "because": f"score {pdd['match']['score']} >= {_DEDUP_THR} dup threshold",
                          "alternatives": ["create a new FERT"]})
                paction = "dedup-reuse"
            else:
                pmat, res = _create_material({**parent, "type": parent.get("type", "FERT")}, plant)
                if not pmat:
                    sp.record("parent", "create FERT", "failed", outcome=res[:160], inputs={"desc": pdesc})
                    gres["parent"] = {"description": pdesc, "material": None, "action": "failed", "dedup": pdd}
                    return _emit(f"GENESIS ABORTED -- parent create failed: {res[:300]}" + _dossier(sp.finalize()), gres)
                report.append(f"parent FERT created: {pmat}  ({pdesc})")
                sp.material = pmat
                sp.record("parent", "create FERT", "created", outcome=f"created {pmat}", obj=_readback(pmat),
                          writes=1, inputs={"desc": pdesc, "type": parent.get("type", "FERT")},
                          decision={"choice": "create a new FERT (born routable)", "because": "no existing material given",
                                    "alternatives": ["reuse an existing FERT"]})
                _vec_add(pmat, (pdesc or "")[:60])   # <-- write-back so a repeat run sees it
                paction = "created"
        gres["parent"] = {"description": pdesc, "material": pmat, "type": parent.get("type", "FERT"),
                          "action": paction, "dedup": pdd}
        sp.add_kg(pmat, "FERT", description=(pdesc or "")[:40], plant=plant)

    # 2) COMPONENTS (+ PIR/cost for bought) ----------------------------------
    comp_rows = []
    for c in comps:
        mat = c.get("material")
        cdesc = c.get("description") or c.get("name") or ""
        sname = f"component:{c.get('name')}"
        cin = {"name": c.get("name"), "type": c.get("type"), "role": c.get("role"),
               "vendor": c.get("vendor"), "price": c.get("price"), "qty": c.get("quantity", 1)}
        crow = {"name": c.get("name"), "description": cdesc, "type": c.get("type"), "role": c.get("role"),
                "quantity": c.get("quantity", 1), "vendor": c.get("vendor"), "price": c.get("price"),
                "material": None, "action": None, "dedup": None, "pir": None, "cost": None}
        if _exists(mat):
            report.append(f"  - {c['name']}: exists {mat}")
            sp.record(sname, "reuse component", "exists", outcome=f"exists {mat}", obj=_readback(mat),
                      inputs=cin, decision={"choice": f"reuse {mat}", "because": "component already in SAP",
                                            "alternatives": ["create a new component"]})
            crow["action"] = "exists"
        else:
            cdd = _dd(cdesc)                          # <-- dedup BEFORE create (skipped if dedup off)
            crow["dedup"] = cdd
            if cdd["is_duplicate"]:
                mat = cdd["match"]["Product"]
                report.append(f"  - {c['name']}: reused {mat} (semantic dup ~{cdd['match']['score']})")
                sp.record(sname, "dedup-reuse component", "exists",
                          outcome=f"reused {mat} (score {cdd['match']['score']})", obj=_readback(mat), inputs=cin,
                          decision={"choice": f"reuse {mat} (semantic match)",
                                    "because": f"score {cdd['match']['score']} >= {_DEDUP_THR} dup threshold",
                                    "alternatives": ["create a new component"]})
                crow["action"] = "dedup-reuse"
            else:
                mat, res = _create_material(c, plant)
                if not mat:
                    report.append(f"  - {c['name']}: CREATE FAILED {res[:120]}")
                    sp.record(sname, "create component", "failed", outcome=res[:120], inputs=cin)
                    crow["action"] = "failed"
                    gres["components"].append(crow)
                    continue
                report.append(f"  - {c['name']}: created {mat} [{c.get('type')}]")
                sp.record(sname, "create component", "created", outcome=f"created {mat}", obj=_readback(mat),
                          writes=1, inputs=cin, decision={"choice": f"create {c.get('type')} component",
                          "because": "no existing material given", "alternatives": ["reuse an existing component"]})
                _vec_add(mat, cdesc[:60])             # <-- write-back
                crow["action"] = "created"
        crow["material"] = mat
        c["material"] = mat                               # hand the created number back for the sub-assembly pass
        comp_rows.append({"component": mat, "quantity": c.get("quantity", 1)})
        sp.material = sp.material or mat                  # components-only run: anchor on the first part
        sp.add_kg(mat, c.get("type", "HAWA"), description=cdesc[:40])
        sp.add_kg(pmat, "FERT", edges=[("uses", mat, {"quantity": c.get("quantity", 1)})])  # no-op if no parent
        if c.get("role") == "bought" and c.get("vendor"):
            # Pass the (web-sourced) price into the PIR too -- not just the cost condition. Without this
            # the info record was born at the create_info_record default net_price=0.01 even though the
            # spec carried a real price, so MD04/purchasing showed 0.01 (session ed478141).
            _pir_price = float(c["price"]) if c.get("price") not in (None, "") else 0.01
            pir = _plain(create_info_record(mat, c["vendor"], net_price=_pir_price, confirm=True))
            ok = "Created" in pir
            report.append(f"      PIR: {'ok' if ok else pir[:90]}")
            crow["pir"] = {"status": "ok" if ok else "failed", "vendor": c.get("vendor"), "message": pir[:120]}
            sp.record(f"source:{c.get('name')}", "create PIR", "created" if ok else "failed",
                      outcome=pir[:90], verified=ok, grounded_by=pir[:90], writes=1 if ok else 0,
                      inputs={"comp": mat, "vendor": c.get("vendor")},
                      decision={"choice": f"source from {c.get('vendor')}", "because": "bought part needs a source",
                                "alternatives": ["make in-house", "an alternate vendor"]})
            sp.add_kg(mat, c.get("type", "HAWA"), edges=[("supplied_by", c["vendor"], {})])
            sp.add_kg(c["vendor"], "vendor")
            if c.get("price"):
                cost = _plain(create_cost_condition(mat, c["vendor"], float(c["price"]), confirm=True))
                cok = "Created" in cost
                report.append(f"      cost: {'ok' if cok else cost[:90]}")
                crow["cost"] = {"status": "ok" if cok else "failed", "price": c.get("price"),
                                "vendor": c.get("vendor"), "message": cost[:120]}
                sp.record(f"cost:{c.get('name')}", "create cost", "created" if cok else "failed",
                          outcome=cost[:90], verified=cok, grounded_by=cost[:90], writes=1 if cok else 0,
                          inputs={"comp": mat, "vendor": c.get("vendor"), "price": c.get("price")})
        gres["components"].append(crow)

    # 3-5) BOM + ROUTING + PRODUCTION VERSION -- ONLY for a manufactured parent. A components-only
    #      run stops here: the parts + their PIR/cost exist; there is nothing to assemble or plan-bind.
    if not has_parent:
        report.append("(components-only -- no BOM / routing / production version)")
        recon = _reconcile_created(None, comps, None, False)          # B1: reconcile BEFORE any "complete"
        gres["reconciliation"] = recon
        gres["discipline"] = _discipline_summary(sp.finalize())
        if not recon["complete"]:
            gres["incomplete"] = recon
            return _emit(f"GENESIS INCOMPLETE (components only) -- created {recon['created']}/"
                         f"{recon['planned']} planned materials:\n" + "\n".join(report)
                         + _recon_lines(recon) + _dossier(sp.finalize()), gres)
        return _emit("GENESIS COMPLETE (components only, reconciled "
                     f"{recon['created']}/{recon['planned']}):\n" + "\n".join(report)
                     + _recon_lines(recon) + _dossier(sp.finalize()), gres)

    # 3) BOM (parent + components) -------------------------------------------
    if comp_rows:
        bom = _plain(create_bom(pmat, plant, comp_rows, confirm=True))
        bok = "created" in bom.lower() or "ok" in bom.lower()
        report.append(f"BOM: {bom[:140]}")
        gres["bom"] = {"status": "ok" if bok else "failed", "components": len(comp_rows), "message": bom[:160]}
        sp.record("bom", "create BOM", "created" if bok else "failed", outcome=bom[:140],
                  verified=bok, grounded_by=bom[:140], writes=1 if bok else 0,
                  inputs={"parent": pmat, "components": comp_rows},
                  decision={"choice": f"BOM of {len(comp_rows)} components",
                            "because": "the assembly needs a structure", "alternatives": ["phantom / no BOM"]})

    # 4) ROUTING (parent) ----------------------------------------------------
    rt = _plain(create_routing(pmat, plant, routing,
                description=f"{(parent.get('description') or '')[:28]} routing", confirm=True))
    rok = "created" in rt.lower() or "ok" in rt.lower()
    report.append(f"ROUTING: {rt[:140]}")
    gres["routing"] = {"status": "ok" if rok else "failed",
                       "operations": [{"operation": o.get("operation"), "text": o.get("text"),
                                       "work_center": o.get("work_center")} for o in routing], "message": rt[:160]}
    sp.record("routing", "create routing", "created" if rok else "failed", outcome=rt[:140],
              verified=rok, grounded_by=rt[:140], writes=1 if rok else 0,
              inputs={"parent": pmat, "ops": routing},
              decision={"choice": " -> ".join(o["work_center"] for o in routing),
                        "because": "a made part needs operations", "alternatives": ["external processing"]})
    for o in routing:
        sp.add_kg(o["work_center"], "work_center")
        sp.add_kg(pmat, "FERT", edges=[("routed_thru", o["work_center"], {"op": o.get("operation")})])

    # 5) PRODUCTION VERSION (MKAL) -- the FINAL master-data object. Part of the OBJECT DESIGN, not
    #    planning: without it MRP can't select the BOM (MD408), so the assembly is not truly
    #    "born MRP-ready" until this binds BOM alt 01 / usage 1. Lives on your remote :8002 server.
    pv_ok, pv_msg = _create_production_version(pmat, plant, parent.get("description"))
    report.append(f"PRODUCTION VERSION (lot 1-10000): {'ok -- ' if pv_ok else 'NOT bound -- '}{pv_msg[:140]}")
    gres["production_version"] = {"status": "ok" if pv_ok else "failed", "version": "0001",
                                  "bom_alt": "01", "bom_usage": "1", "lot": "1-10000", "message": pv_msg[:160]}
    sp.record("production_version", "create production version (MKAL @ :8002, lot 1-10000)",
              "created" if pv_ok else "failed", outcome=pv_msg[:140],
              verified=pv_ok, grounded_by=pv_msg[:140], writes=1 if pv_ok else 0,
              inputs={"parent": pmat, "version": "0001", "bom_alt": "01", "bom_usage": "1",
                      "lot_min": "1", "lot_max": "10000"},
              decision={"choice": "bind BOM alt 01 / usage 1 as version 0001, lot size 1-10000",
                        "because": "without the MKAL the BOM can't be selected by MRP (MD408)",
                        "alternatives": ["leave unbound -- NOT MRP-ready"]})
    sp.add_kg(f"PV-{pmat}-0001", "production_version", bound_bom="alt 01 / usage 1")
    sp.add_kg(pmat, "FERT", edges=[("has_production_version", f"PV-{pmat}-0001", {})])

    # 6) SUB-ASSEMBLIES -- every MADE component that carries its OWN children gets its own BOM +
    #    routing + production version, so the assembly is multi-level and born MRP-ready at EVERY made
    #    node (no board NO-GO / heal pass needed for the HALB sub-structure). Shared raws (epoxy, bolts,
    #    CF sheet) are created ONCE and referenced across HALBs. No-op for a flat spec.
    created_raws: dict = {}
    subs = []
    for c in comps:
        if c.get("role") == "made" and c.get("components"):
            sub = _build_made_subassembly(c, plant, sp, report, created_raws, _dd)
            if sub:
                subs.append(sub)
    if subs:
        gres["subassemblies"] = subs
        report.append(f"SUB-ASSEMBLIES: {len(subs)} made node(s) given their own BOM + routing + "
                      f"production version ({len(created_raws)} raw material(s) created/deduped)")

    final = sp.finalize()
    gres["discipline"] = _discipline_summary(final)
    recon = _reconcile_created(parent, comps, pmat, has_parent)       # B1: reconcile BEFORE any "complete"
    gres["reconciliation"] = recon
    if not recon["complete"]:
        gres["incomplete"] = recon
        return _emit(f"GENESIS INCOMPLETE for {pmat} -- created {recon['created']}/{recon['planned']} "
                     f"planned materials ({len(recon['missing'])} MISSING):\n" + "\n".join(report)
                     + _recon_lines(recon) + _dossier(final), gres)
    return _emit(f"GENESIS COMPLETE for {pmat} (reconciled {recon['created']}/{recon['planned']}):\n"
                 + "\n".join(report)
                 + _recon_lines(recon)
                 + _dossier(final), gres)            # S6/S8 persist + roll-up, then append the dossier


# ---- B6: ONE-CALL plant ENABLEMENT -----------------------------------------------------------
# The painful manual sequence (extend FG + every component -> work-scheduling view -> set a planning
# MRP type + a grounded controller -> BOM -> routing on a grounded work center -> production version
# -> optional demand + MRP), orchestrated deterministically, with grounding built in. This is the
# EXTENSION twin of run_genesis: run_genesis BIRTHS an assembly at its first plant; this REPLICATES an
# existing one at a NEW plant so it comes out plannable AND producible there.
def _ok(s) -> bool:
    """A tool's human string reports success unless it carries a failure marker."""
    s = str(s).lower()
    return not any(x in s for x in ("failed", "error", "could not", "aborted", "not found", "invalid",
                                    "blocked", "not valid"))


def _source_bom_components(material: str, plant: str) -> list[dict]:
    """An existing BOM's components via the PROVEN make reader (tries the common alternatives), as
    [{"component","quantity"}] -- [] if none. make._get_bom uses $expand=to_BillOfMaterialItem and is
    reliable; assurance._read_bom_components misses the expand on some materials and returns nothing."""
    from make import _get_bom
    for alt in ("1", "01", "2"):
        got = _get_bom(material, plant, alt)
        if not got:
            continue
        _num, items = got
        rows = []
        for it in items:
            comp = it.get("BillOfMaterialComponent") or it.get("Material")
            qty = it.get("BillOfMaterialComponentQuantity") or it.get("BillOfMaterialItemQuantity") or 1
            if comp:
                rows.append({"component": str(comp).strip(), "quantity": qty})
        if rows:
            return rows
    return []


@mcp.tool()
def enable_plant_production(material: str, plant: str, components: list | None = None,
                           mrp_controller: str = "", work_center: str = "", mrp_type: str = "PD",
                           source_plant: str = "", demand_qty: float = 0, confirm: bool = False) -> str:
    """Make an EXISTING assembly plannable AND producible at a NEW plant in ONE grounded call.

    The full sequence we otherwise run by hand, in order:
      1. extend the FG + every BOM component to the plant (A_ProductPlant + valuation)
      2. add the FG's work-scheduling view (the routing + production version need it)
      3. set a planning MRP type (PD) + a GROUNDED MRP controller on the FG + components
      4. build the plant BOM (FG + components)
      5. create a routing on a GROUNDED plant work center
      6. bind production version 0001 (so MRP can select the BOM -- clears MD408)
      7. (optional) create demand + run MRP

    GROUNDED against the plant's real config (config-graph): the MRP controller and work center are
    resolved for THIS plant and never another plant's, and the plant config is validated BEFORE any
    write. Each underlying write is a proven, individually confirm-gated tool.

    SAFETY GATE: confirm=false (default) returns the grounded PLAN -- the resolved controller / work
    center / components and the exact ordered steps -- and writes NOTHING. confirm=true executes.

    Args:
        material:    the FERT assembly (already created at its birth plant).
        plant:       the TARGET plant to enable (e.g. "1010").
        components:  [{"component": matnr, "quantity": q}] or [matnr, ...]; omitted -> read the
                     source-plant BOM.
        mrp_controller: DISPO for the plant; default = first valid controller for the plant.
        work_center:    routing work center; default = first valid work center for the plant.
        mrp_type:    planning MRP type for the FG + components (default "PD"; "ND" = no planning).
        source_plant: plant to read the existing BOM from (default = SAP_PLANT birth plant).
        demand_qty:  if > 0, create demand for this qty and run MRP after enabling.
        confirm:     must be true to write.
    """
    src = source_plant or _DEF_PLANT
    planning = (mrp_type or "").strip().upper() not in ("", "ND", "X0")

    # --- GROUND the plant config FIRST: a controller + a work center valid for THIS plant ----------
    from config_graph import get_relation, validate_plant_config        # lazy: only a call needs the RFC
    ctrls = get_relation("mrp_controller", plant)
    if ctrls.get("error"):
        return _emit(f"ENABLE ABORTED -- cannot read plant {plant} config: {ctrls['error']}",
                     {"kind": "enable", "plant": plant, "error": ctrls["error"]})
    ctrl_codes = [v["code"] for v in ctrls.get("values", [])]
    ctrl = (mrp_controller or (ctrl_codes[0] if ctrl_codes else "")).strip()
    cfg = validate_plant_config(plant, mrp_controller=(ctrl if planning else None), mrp_type=mrp_type)
    if cfg:
        return _emit("ENABLE ABORTED -- plant config not grounded:\n  - " + "\n  - ".join(cfg),
                     {"kind": "enable", "plant": plant, "problems": cfg})

    from make import _load_work_centers, _resolve_work_center           # lazy
    if work_center:
        iid, _ = _resolve_work_center(work_center, plant)
        if not iid:
            known = [w.get("work_center") for w in _load_work_centers().get(str(plant), [])]
            return _emit(f"ENABLE ABORTED -- work center {work_center!r} not valid for plant {plant}. "
                         f"Known: {known}", {"kind": "enable", "plant": plant, "work_centers": known})
        wc = work_center
    else:
        wcs = _load_work_centers().get(str(plant), [])
        if not wcs:
            return _emit(f"ENABLE ABORTED -- no work centers known for plant {plant} (the routing needs one).",
                         {"kind": "enable", "plant": plant})
        wc = wcs[0].get("work_center")

    # --- resolve the components (passed, or read the source-plant BOM) -----------------------------
    comp_rows = []
    if components:
        for c in components:
            if isinstance(c, dict):
                comp_rows.append({"component": str(c.get("component") or c.get("material") or "").strip(),
                                  "quantity": c.get("quantity", 1)})
            else:
                comp_rows.append({"component": str(c).strip(), "quantity": 1})
    else:
        comp_rows = _source_bom_components(material, src)               # proven make reader (tries alts)
    comp_rows = [c for c in comp_rows if c["component"] and c["component"].lower() != "none"]

    if not _exists(material):
        return _emit(f"ENABLE ABORTED -- FG {material} not found (create it first, then enable a plant).",
                     {"kind": "enable", "plant": plant, "material": material})

    ctrl_text = next((v["text"] for v in ctrls.get("values", []) if v["code"] == ctrl), "")
    steps = [f"extend FG {material} (FERT) -> plant {plant}",
             f"add work-scheduling view to {material} @ {plant}"]
    if planning:
        steps.append(f"set MRP {mrp_type} + controller {ctrl} ({ctrl_text}) on FG + {len(comp_rows)} components")
    steps += [f"extend {len(comp_rows)} components -> plant {plant}",
              f"BOM: {material} + {len(comp_rows)} components @ {plant}",
              f"routing: op 10 'Final Assembly' @ work center {wc}",
              "production version 0001 (bind BOM alt 01 / usage 1, lot 1-10000)"]
    if demand_qty and demand_qty > 0:
        steps.append(f"create demand {demand_qty:g} + run MRP @ {plant}")

    plan = {"kind": "enable", "mode": "preview" if not confirm else "complete", "material": material,
            "plant": plant, "source_plant": src, "mrp_type": mrp_type, "mrp_controller": ctrl,
            "mrp_controller_text": ctrl_text, "work_center": wc, "components": comp_rows,
            "demand_qty": demand_qty, "steps": steps}

    if not confirm:
        body = ["ENABLE-PLANT PREVIEW -- nothing written. Confirm to run the full sequence.",
                f"  FG: {material}   target plant: {plant}   (BOM source: {src})",
                f"  grounded -> MRP {mrp_type} / controller {ctrl} ({ctrl_text}); work center {wc}",
                f"  components ({len(comp_rows)}): {', '.join(c['component'] for c in comp_rows) or '(none found)'}",
                "  steps:"] + [f"    {i + 1}. {s}" for i, s in enumerate(steps)]
        return _emit("\n".join(body), plan)

    # ---- EXECUTE (confirm=true) ------------------------------------------------------------------
    report, results = [], {}

    # 1) extend FG (FERT) + 2) work-scheduling view
    report.append(f"extend FG {material} (FERT): {'ok' if _ok(r := extend_to_plant(material, plant, product_type='FERT', mrp_type='ND', confirm=True)) else r[:160]}")
    report.append(f"work-scheduling view: {'ok' if _ok(r := change_material_view('A_ProductWorkScheduling', {'Product': material, 'Plant': plant}, {}, operation='add', confirm=True)) else r[:160]}")

    # 3) extend each component by ITS type, then set the planning MRP on the FG + components
    targets = [material]
    for c in comp_rows:
        ctype = (_readback(c["component"]) or {}).get("ProductType", "ROH")
        r = extend_to_plant(c["component"], plant, product_type=ctype, mrp_type="ND", confirm=True)
        report.append(f"extend {c['component']} ({ctype}): {'ok' if _ok(r) else r[:120]}")
        targets.append(c["component"])
    if planning:
        for mat in targets:
            # MRP type + controller + lot size live on the supply-planning view (mirrors what genesis
            # nests at birth). Adding the row is the proven write; an existing row -> update instead.
            fields = {"MRPType": mrp_type, "MRPResponsible": ctrl, "LotSizingProcedure": "EX"}
            r = change_material_view("A_ProductSupplyPlanning", {"Product": mat, "Plant": plant},
                                     fields, operation="add", confirm=True)
            if not _ok(r):
                r = change_material_view("A_ProductSupplyPlanning", {"Product": mat, "Plant": plant},
                                         fields, operation="update", confirm=True)
            report.append(f"MRP {mrp_type}/{ctrl} on {mat}: {'ok' if _ok(r) else r[:120]}")

    # 4) BOM, 5) routing on the grounded work center, 6) production version
    results["bom_ok"] = _ok(r := create_bom(material, plant, comp_rows, confirm=True))
    report.append(f"BOM ({len(comp_rows)} comps): {'ok' if results['bom_ok'] else r[:160]}")
    # ROUTING has no natural key -- unlike the BOM (alt 1/usage 1) and production version (0001), a
    # re-run of create_routing mints a BRAND NEW routing group every time, leaving duplicates behind
    # (session 5fc3f68b: 3 retries of enable_plant_production -> 3 orphaned routing groups on one FERT).
    # Check for an EXISTING routing FIRST; only create if none, so a retry is a safe no-op.
    _existing_rt = json.loads(read_routing(material, plant) or "{}")
    if _existing_rt.get("present") is True:
        results["routing_ok"] = True
        _grp = (_existing_rt.get("routings") or [{}])[0].get("group")
        report.append(f"routing @ {wc}: reuse existing (group {_grp}) -- already present, not re-created")
    else:
        results["routing_ok"] = _ok(r := create_routing(
            material, plant, [{"operation": "10", "text": "Final Assembly", "work_center": wc}],
            description=f"{material} routing", confirm=True))
        report.append(f"routing @ {wc}: {'ok' if results['routing_ok'] else r[:160]}")
    pv_ok, pv_msg = _create_production_version(material, plant, material)
    results["prodver_ok"] = pv_ok
    report.append(f"production version 0001: {'ok' if pv_ok else 'NOT bound'} -- {pv_msg[:140]}")

    # 7) optional demand + MRP
    if demand_qty and demand_qty > 0:
        from planning_client import create_demand, run_mrp
        report.append(f"demand {demand_qty:g}: {str(create_demand(material, plant, str(int(demand_qty))))[:140]}")
        results["mrp"] = str(run_mrp(material, plant))[:400]
        report.append(f"MRP run: {results['mrp'][:200]}")

    producible = results.get("bom_ok") and results.get("routing_ok") and results.get("prodver_ok")
    verdict = ("PLANNABLE + PRODUCIBLE" if (producible and planning) else
               "PRODUCIBLE" if producible else "INCOMPLETE -- see steps")
    plan["results"], plan["verdict"] = results, verdict
    return _emit(f"ENABLE-PLANT {verdict} for {material} @ {plant}:\n" + "\n".join(report), plan)


if __name__ == "__main__":
    mcp.run(transport="stdio")
