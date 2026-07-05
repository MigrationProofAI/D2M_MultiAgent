"""plan_card.py -- render the pre-genesis PLAN as a CSS-only TABBED card (Materials|PIRs|Cost|BOMs|Routings|
PVs|Board). Deterministic HTML from plan_report()'s data. The panel executes no JS, so tabs are radio +
:checked (works because the Structured-Data panel renders card HTML raw). Reuses verification_cards helpers."""
from verification_cards import _e, _wrap, _header, _footer, _chips, _badge, _NAVY, _OK, _BAD, _PROV_COLOR


def _prov(tag):
    base = str(tag).split(":", 1)[0]
    col = _PROV_COLOR.get(base, "#8a8f98")
    return (f'<span style="background:{col};color:#fff;border-radius:3px;padding:1px 6px;'
            f'font-size:10px">{_e(tag)}</span>')


def _ctable(rows):
    tr = "".join(
        f'<tr style="border-bottom:1px solid #eee">'
        f'<td style="padding:5px 10px;color:#888;font-size:11px">{_e(v)}</td>'
        f'<td style="padding:5px 10px;font-weight:600">{_e(f)}</td>'
        f'<td style="padding:5px 10px;color:#333">{_e(val)}</td>'
        f'<td style="padding:5px 10px">{_prov(p)}</td></tr>'
        for v, f, val, p in rows)
    return ('<table style="width:100%;border-collapse:collapse;font-size:12px">'
            '<thead><tr style="background:#eef2f7;color:#456">'
            '<th style="padding:6px 10px;text-align:left">View</th>'
            '<th style="padding:6px 10px;text-align:left">Field</th>'
            '<th style="padding:6px 10px;text-align:left">Value / rule</th>'
            '<th style="padding:6px 10px;text-align:left">Source</th></tr></thead>'
            f'<tbody>{tr}</tbody></table>')


def _rows_table(headers, rows):
    th = "".join(f'<th style="padding:5px 10px;text-align:left">{_e(h)}</th>' for h in headers)
    tr = "".join('<tr style="border-bottom:1px solid #f0f0f0">'
                 + "".join(f'<td style="padding:4px 10px">{_e(x)}</td>' for x in r) + '</tr>' for r in rows)
    return (f'<div style="max-height:340px;overflow:auto;border:1px solid #eee;border-radius:6px">'
            f'<table style="width:100%;border-collapse:collapse;font-size:12px">'
            f'<thead><tr style="background:#f4f7fb;color:#456">{th}</tr></thead>'
            f'<tbody>{tr}</tbody></table></div>')


def _section(title, *blocks):
    return (f'<div style="font-size:12px;font-weight:700;color:#456;margin:8px 0 6px">{_e(title)}</div>'
            + "".join(blocks))


def plan_card(data, board=None):
    c = data.get("counts", {})
    cost = data.get("total_cost", 0)
    fert = data.get("fert", {})
    gid = "gp" + str(abs(sum(ord(x) for x in str(fert.get("description", "")) + str(c))) % 100000)
    contract = data.get("contract", {})

    chips = _chips([("MATERIALS", c.get("materials", 0), "#333"), ("MADE", c.get("made", 0), "#333"),
                    ("BOUGHT", c.get("bought", 0), "#333"), ("LEVELS", c.get("depth", 0), "#333"),
                    ("PURCHASED COST", f"${cost:,.0f}", _NAVY)])
    cbs = data.get("cost_by_system", {})
    sys_rows = _rows_table(["System", "Purchased cost"], [[k, f"${v:,.2f}"] for k, v in cbs.items()])
    fl = "".join(
        f'<div style="padding:3px 0;color:{_BAD if lvl in ("warn","bad") else (_OK if lvl=="ok" else "#666")}">'
        f'{"⚠" if lvl in ("warn","bad") else ("✓" if lvl=="ok" else "·")} {_e(msg)}</div>'
        for lvl, msg in data.get("flags", []))
    mat_rows = [[m["name"], m["type"], m["role"], m.get("vendor") or "—",
                 (f'${m["price"]}' if m.get("price") not in (None, "") else "—"),
                 (", ".join(f"{k}={v}" for k, v in (m.get("attrs") or {}).items()) or "—")]
                for m in data.get("materials", [])]
    mat_panel = (chips + _section("Cost by system", sys_rows)
                 + _section("Flags", f'<div style="font-size:12px">{fl}</div>')
                 + _section("Material field contract", _ctable(contract.get("Materials", [])))
                 + _section(f"Materials ({len(mat_rows)})",
                            _rows_table(["Material", "Type", "Role", "Vendor", "Price", "Attributes"], mat_rows)))

    pir_rows = [[p["part"], p.get("vendor") or "—",
                 f'${p.get("price")}' if p.get("price") not in (None, "") else "—", p.get("system") or ""]
                for p in data.get("pirs", [])]
    pir_panel = (_section("PIR field contract", _ctable(contract.get("Purchase Info Records", [])))
                 + _section(f"Purchase info records ({len(pir_rows)})",
                            _rows_table(["Bought part", "Supplier", "Net price", "System"], pir_rows)))

    cost_rows = [[x["part"], x.get("condition"), f'${x.get("rate")}', x.get("vendor") or "—"]
                 for x in data.get("costs", [])]
    cost_panel = (_section("Cost condition contract", _ctable(contract.get("Cost Conditions", [])))
                  + _section(f"Cost conditions ({len(cost_rows)})",
                             _rows_table(["Bought part", "Condition", "Rate", "Supplier"], cost_rows)))

    bom_rows = [[b["parent"], b["type"], f'{len(b["components"])} comp',
                 ", ".join(x["name"] for x in b["components"][:6]) + ("…" if len(b["components"]) > 6 else "")]
                for b in data.get("boms", [])]
    bom_panel = (_section("BOM field contract", _ctable(contract.get("Bills of Material", [])))
                 + _section(f"BOMs ({len(bom_rows)})",
                            _rows_table(["Parent (made)", "Type", "Items", "Components"], bom_rows)))

    wcs = data.get("work_centers", [])
    rt_rows = [[r["node"], " → ".join(o["wc"] for o in r["operations"]), str(len(r["operations"]))]
               for r in data.get("routings", [])]
    rt_panel = (_section(f"Work centers used ({len(wcs)})",
                         f'<div style="font-size:12px;color:#333">{_e(", ".join(wcs))}</div>')
                + _section("Routing field contract", _ctable(contract.get("Routings", [])))
                + _section(f"Routings ({len(rt_rows)})",
                           _rows_table(["Made node", "Work-center sequence", "Ops"], rt_rows)))

    pv_rows = [[p["node"], p["version"], p["binding"], p["lot"]] for p in data.get("pvs", [])]
    pv_panel = (_section("Production version contract", _ctable(contract.get("Production Versions", [])))
                + _section(f"Production versions ({len(pv_rows)})",
                           _rows_table(["Made node", "Version", "Binding", "Lot size"], pv_rows)))

    if board:
        v = board.get("verdict", "")
        vcol = _OK if ("GO" in v.upper() and "NO-GO" not in v.upper()) else _BAD
        def vote_col(vt):
            return _OK if ("GO" in (vt or "").upper() and "NO-GO" not in (vt or "").upper()) else _BAD
        members = "".join(
            f'<div style="padding:6px 0;border-bottom:1px solid #eee"><b>{_e(m.get("func"))}</b> '
            f'{_badge(m.get("vote","") or "?", vote_col(m.get("vote","")))}'
            f'<div style="color:#555;font-size:12px;margin-top:2px">{_e(m.get("note",""))[:400]}</div></div>'
            for m in (board.get("members") or []))
        board_panel = (f'<div style="font-size:16px;font-weight:bold;color:{vcol};margin-bottom:8px">{_e(v)}</div>'
                       + f'<div style="font-size:12px;color:#444;white-space:pre-wrap">{_e(board.get("text",""))[:1200]}</div>'
                       + (_section("Function votes", members) if members else ""))
    else:
        board_panel = ('<div style="color:#888;font-size:13px">Board review runs on this plan — the '
                       'cross-functional GO/NO-GO appears here and in the chat.</div>')

    tabs = [("Materials", mat_panel), ("PIRs", pir_panel), ("Cost", cost_panel), ("BOMs", bom_panel),
            ("Routings", rt_panel), ("PVs", pv_panel), ("Board", board_panel)]

    css = [f"#{gid} .rin{{position:absolute;opacity:0;width:0;height:0}}",
           f"#{gid} .tabbar{{display:flex;flex-wrap:wrap;background:#eef2f7;border-bottom:1px solid #d0d0d0}}",
           f"#{gid} .tablbl{{padding:8px 13px;cursor:pointer;font-size:12.5px;color:#567;"
           f"border-bottom:3px solid transparent;user-select:none}}",
           f"#{gid} .panel{{display:none;padding:12px 16px}}"]
    inputs, labels, panels = [], [], []
    for k, (name, body_) in enumerate(tabs):
        rid = f"{gid}_r{k}"
        inputs.append(f'<input class="rin" type="radio" name="{gid}" id="{rid}"{" checked" if k == 0 else ""}>')
        labels.append(f'<label class="tablbl" for="{rid}">{_e(name)}</label>')
        panels.append(f'<div class="panel" id="{gid}_p{k}">{body_}</div>')
        css.append(f'#{gid} #{rid}:checked ~ .tabbar label[for="{rid}"]'
                   f'{{color:{_NAVY};font-weight:700;border-bottom-color:{_NAVY}}}')
        css.append(f'#{gid} #{rid}:checked ~ .panels #{gid}_p{k}{{display:block}}')
    head = _header("Genesis Plan — pre-commit review", f"Plant {data.get('plant', '')}")
    body = (f'<div class="gp" id="{gid}" style="font-family:Arial,sans-serif;max-width:900px;'
            f'border:1px solid #d0d0d0;border-radius:8px;overflow:hidden">'
            f'<style>{"".join(css)}</style>{head}{"".join(inputs)}'
            f'<div class="tabbar">{"".join(labels)}</div>'
            f'<div class="panels">{"".join(panels)}</div>'
            f'{_footer("Deterministic pre-genesis contract · " + str(c.get("materials", 0)) + " materials · ~0 LLM tokens")}</div>')
    sub = (f"{c.get('materials', 0)} materials · {c.get('depth', 0)} levels · ${cost:,.0f} purchased"
           + (f" · BOARD {board.get('verdict', '')}" if board else ""))
    return _wrap("Genesis Plan", sub, body)


def conformance_card(data):
    """Render the CONFORMANCE audit (actual SAP vs intended contract) as a card: per-object conform counts,
    verdict, and the non-conforming diffs (intended vs actual). Deterministic HTML from conformance.data."""
    by = data.get("by_object", {})
    diffs = [f for f in data.get("findings", []) if not f.get("conforms")]
    passed = data.get("passed")
    chips = _chips([(o.upper(), f"{t - d}/{t}", (_BAD if d else _OK)) for o, (t, d) in by.items()]
                   + [("VERDICT", "CONFORMS" if passed else f"{len(diffs)} DIFF", (_OK if passed else _BAD))])
    # split missing vs drift for the reader
    def _kind(f):
        return "MISSING" if (f.get("field") == "exists" or str(f.get("actual")).upper() in ("NONE", "NOT FOUND")) else "DRIFT"
    rows = [[f.get("mat") or "—", f'{f.get("object")}.{f.get("field")}', _kind(f),
             str(f.get("intended"))[:34], str(f.get("actual"))[:34]] for f in diffs]
    body_rows = (_rows_table(["Material", "Object.field", "Kind", "Intended (plan)", "Actual (SAP)"], rows)
                 if rows else '<div style="color:#1e874b;padding:8px">Every field matches the approved plan.</div>')
    head = _header("Conformance Audit — actual SAP vs intended contract", f"Plant {data.get('plant', '')}")
    checks = data.get("checks", 0)
    title = f"Non-conforming fields ({len(diffs)} of {checks} checks)"
    body = (f'<div style="font-family:Arial,sans-serif;max-width:860px;border:1px solid #d0d0d0;'
            f'border-radius:8px;overflow:hidden">{head}{chips}'
            f'<div style="padding:12px 16px">{_section(title, body_rows)}</div>'
            f'{_footer("Deterministic conformance audit · " + str(checks) + " field checks · ~0 LLM tokens")}</div>')
    sub = f"{checks} checks · " + ("CONFORMS ✓" if passed else f"{len(diffs)} non-conforming")
    return _wrap("Conformance Audit", sub, body)


def routing_recon_card(data):
    """Render the PRE-vs-POST routing reconciliation: per made node, planned vs actual work centers + status."""
    rows = data.get("rows", [])
    match, drift, miss = data.get("match", 0), data.get("drift", 0), data.get("missing", 0)
    passed = not drift and not miss
    chips = _chips([("MADE NODES", data.get("made", 0), "#333"), ("MATCH", match, _OK),
                    ("DRIFT", drift, (_BAD if drift else "#333")), ("MISSING", miss, (_BAD if miss else "#333")),
                    ("VERDICT", "ALL MATCH" if passed else "DRIFT", (_OK if passed else _BAD))])
    nc = data.get("not_created", [])
    cov = (f'<div style="font-size:12px;color:#333;padding:2px 0">work centers: planned '
           f'<b>{len(data.get("planned_wcs", []))}</b> → created <b>{len(data.get("actual_wcs", []))}</b>'
           + (f' · <span style="color:{_BAD}">not created (invalid for routings): {", ".join(nc)}</span>' if nc else "")
           + '</div>')
    scol = {"MATCH": _OK, "DRIFT": _BAD, "MISSING": _BAD, "NO-MATERIAL": _BAD}
    trs = []
    for r in rows:
        st = r["status"]
        trs.append([r["mat"] or "—", (r["node"] or "")[:32], " > ".join(w for w in r["planned"] if w),
                    " > ".join(w for w in r["actual"] if w) or "—", r.get("group") or "—", st])
    tbl = _rows_table(["Material", "Made node", "Planned WCs (pre)", "Actual WCs (post)", "Group", "Status"], trs)
    head = _header("Routing Reconciliation — planned vs actual", f"Plant {data.get('plant', '')}")
    body = (f'<div style="font-family:Arial,sans-serif;max-width:900px;border:1px solid #d0d0d0;'
            f'border-radius:8px;overflow:hidden">{head}{chips}'
            f'<div style="padding:12px 16px">{cov}{_section(f"Routings ({len(rows)} made nodes)", tbl)}</div>'
            f'{_footer("Deterministic routing recon · planned (spec) vs actual (SAP) · ~0 LLM tokens")}</div>')
    sub = f"{data.get('made', 0)} nodes · {match} match / {drift} drift / {miss} missing"
    return _wrap("Routing Reconciliation", sub, body)
