"""verification_cards.py -- render the deterministic verifiers' structured output as Structured-Data-panel
CARDS, in Python, at ~0 tokens.

The rig's card skills (md04-card-skill, independent-certification-report, ...) are AGENT-driven: the LLM
binds data, writes the HTML from a TEMPLATE, and calls render_card. That costs tokens and reintroduces LLM
variance -- untenable for a 150-row table. Our verifiers already hold the exact structured data, so we build
the same card HTML deterministically here and hand web.py a `render_card`-shaped result string
(`<readable>@@DATA@@{kind:"card",...}`) that rides the existing @@DATA@@ -> _cards forwarder. No frontend
rebuild, no LLM, no variance. This module is the RENDERER; the skill TEMPLATE is the visual contract."""
import json
from html import escape

_PROV_COLOR = {"file": "#1e874b", "derived": "#2c6fbb", "default": "#8a8f98",
               "metadata": "#6a4fb0", "SAP": "#b9770e"}

_NAVY = "#1a3c5e"
_OK = "#1e874b"
_BAD = "#c0392b"
_WARN = "#b9770e"
_MADE = {"FERT", "HALB"}


def _e(v):
    return escape(str(v if v is not None else ""))


def _wrap(title, subtitle, body_html):
    """The render_card-shaped result: readable line + @@DATA@@ card payload that _cards forwards."""
    payload = {"kind": "card", "title": title, "subtitle": subtitle, "content": body_html}
    return (f"Rendered '{title}' into the Structured Data panel.\n"
            "@@DATA@@" + json.dumps(payload, ensure_ascii=False))


def _header(title, right):
    return (f'<div style="background:{_NAVY};color:#fff;padding:12px 16px;display:flex;'
            f'justify-content:space-between;align-items:center">'
            f'<span style="font-size:18px;font-weight:bold">{_e(title)}</span>'
            f'<span style="font-size:12px;opacity:0.85">{_e(right)}</span></div>')


def _chips(pairs):
    cells = "".join(
        f'<div><div style="font-size:10px;color:#666">{_e(k)}</div>'
        f'<div style="font-weight:bold;font-size:15px;color:{c}">{_e(v)}</div></div>'
        for k, v, c in pairs)
    n = len(pairs)
    return (f'<div style="background:#f4f7fb;padding:10px 16px;display:grid;'
            f'grid-template-columns:repeat({n},1fr);gap:8px;border-bottom:1px solid #d0d0d0">{cells}</div>')


def _footer(text):
    return (f'<div style="background:{_NAVY};color:#fff;padding:6px 16px;font-size:11px;'
            f'text-align:right;opacity:0.9">{_e(text)}</div>')


def _badge(text, color):
    return (f'<span style="background:{color};color:#fff;border-radius:4px;padding:2px 7px;'
            f'font-size:11px">{_e(text)}</span>')


# ---- Genesis (post-genesis object verification) -----------------------------------------------------
def genesis_card(data):
    rows = data.get("rows") or []
    passed = data.get("passed")
    verdict = "ALL OBJECTS VERIFIED" if passed else f"{data.get('missing', 0)} MISSING"
    vcol = _OK if passed else _BAD
    head = _header("Genesis Verification — independent SAP read-back",
                   f"Plant {data.get('plant', '')}")
    chips = _chips([
        ("MATERIALS", f"{data.get('confirmed', 0)}/{data.get('total', 0)}", "#333"),
        ("MADE", data.get("made", 0), "#333"),
        ("BOUGHT", data.get("bought", 0), "#333"),
        ("UNVERIFIED", data.get("unverified", 0), _WARN if data.get("unverified") else "#333"),
        ("VERDICT", verdict, vcol)])
    th = ('<tr style="background:#e8edf3;color:#333">'
          '<th style="padding:7px 10px;text-align:left">Material</th>'
          '<th style="padding:7px 10px;text-align:left">Type</th>'
          '<th style="padding:7px 10px;text-align:left">BOM / PIR</th>'
          '<th style="padding:7px 10px;text-align:left">Routing / Cost</th>'
          '<th style="padding:7px 10px;text-align:center">Prod.Ver.</th></tr>')
    trs = []
    for r in sorted(rows, key=lambda x: int(x["mat"]) if str(x["mat"]).isdigit() else 0):
        o = r.get("objects") or {}
        made = r.get("type") in _MADE
        a, b, c = ("BOM", "routing", "production version") if made else ("PIR", "cost condition", None)

        def cell(key):
            d = o.get(key) or {}
            st = d.get("status")
            if st == "ok":
                return f'<span style="color:{_OK}">{_e(d.get("id") or "✓")}</span>'
            if st == "missing":
                return _badge("MISSING", _BAD)
            if st == "unread":
                return _badge("unread", _WARN)
            return ""
        c3 = cell(c) if c else '<span style="color:#bbb">—</span>'
        trs.append(f'<tr style="border-bottom:1px solid #eee">'
                   f'<td style="padding:6px 10px;font-weight:bold">{_e(r["mat"])}</td>'
                   f'<td style="padding:6px 10px;color:#555">{_e(r.get("type"))}</td>'
                   f'<td style="padding:6px 10px">{cell(a)}</td>'
                   f'<td style="padding:6px 10px">{cell(b)}</td>'
                   f'<td style="padding:6px 10px;text-align:center">{c3}</td></tr>')
    table = (f'<table style="width:100%;border-collapse:collapse;font-size:13px"><thead>{th}</thead>'
             f'<tbody>{"".join(trs)}</tbody></table>')
    miss = ""
    if data.get("missing_list"):
        miss = (f'<div style="background:#fdecea;color:{_BAD};padding:8px 16px;font-size:12px;'
                f'border-top:1px solid #f5c6cb"><strong>MISSING:</strong> '
                f'{_e(", ".join(data["missing_list"][:40]))}</div>')
    body = (f'<div style="font-family:Arial,sans-serif;max-width:820px;border:1px solid #d0d0d0;'
            f'border-radius:8px;overflow:hidden">{head}{chips}'
            f'<div style="max-height:520px;overflow:auto">{table}</div>{miss}'
            f'{_footer("Deterministic verifier · read from SAP · ~0 LLM tokens")}</div>')
    sub = f"{data.get('confirmed', 0)}/{data.get('total', 0)} materials · {verdict}"
    return _wrap("Genesis Verification", sub, body)


# ---- MRP tree ---------------------------------------------------------------------------------------
def mrp_tree_card(data):
    nodes = data.get("nodes") or []
    passed = data.get("verdict", "").startswith("PASS")
    vcol = _OK if passed else _BAD
    made = [n for n in nodes if n.get("type") in _MADE]
    bought = [n for n in nodes if n.get("type") not in _MADE]
    po = sum(1 for n in made if n.get("got") == "planned_order")
    pr = sum(1 for n in bought if n.get("got") == "purchase_req")
    cov = sum(1 for n in nodes if n.get("covered"))
    head = _header(f"MRP Tree — {data.get('root', '')}", f"Plant {data.get('plant', '')}")
    chips = _chips([
        ("PLANNED ORDERS", f"{po}/{len(made)}", "#333"),
        ("PURCHASE REQS", f"{pr}/{len(bought)}", "#333"),
        ("DEMAND COVERED", f"{cov}/{len(nodes)}", "#333"),
        ("VERDICT", data.get("verdict", ""), vcol)])
    th = ('<tr style="background:#e8edf3;color:#333">'
          '<th style="padding:7px 10px;text-align:left">Material</th>'
          '<th style="padding:7px 10px;text-align:left">Type</th>'
          '<th style="padding:7px 10px;text-align:left">Element</th>'
          '<th style="padding:7px 10px;text-align:left">Number</th>'
          '<th style="padding:7px 10px;text-align:right">Qty</th>'
          '<th style="padding:7px 10px;text-align:left">Date</th></tr>')
    trs = []
    for n in sorted(nodes, key=lambda x: (x.get("depth", 0), x.get("mat"))):
        s = n.get("supply") or {}
        got = n.get("got")
        if got == "planned_order":
            elem = _badge("PlndOrder", "#2c6fbb")
        elif got == "purchase_req":
            elem = _badge("PurchReq", "#6a4fb0")
        elif n.get("ok") is None:
            elem = _badge("unread", _WARN)
        else:
            elem = _badge("NONE", _BAD)
        indent = 8 + 14 * int(n.get("depth", 0))
        trs.append(f'<tr style="border-bottom:1px solid #eee">'
                   f'<td style="padding:6px 10px;padding-left:{indent}px;font-weight:bold">{_e(n.get("mat"))}</td>'
                   f'<td style="padding:6px 10px;color:#555">{_e(n.get("type"))}</td>'
                   f'<td style="padding:6px 10px">{elem}</td>'
                   f'<td style="padding:6px 10px">{_e(s.get("number"))}</td>'
                   f'<td style="padding:6px 10px;text-align:right">{_e(s.get("qty"))}</td>'
                   f'<td style="padding:6px 10px;color:#555">{_e(s.get("date"))}</td></tr>')
    table = (f'<table style="width:100%;border-collapse:collapse;font-size:13px"><thead>{th}</thead>'
             f'<tbody>{"".join(trs)}</tbody></table>')
    body = (f'<div style="font-family:Arial,sans-serif;max-width:820px;border:1px solid #d0d0d0;'
            f'border-radius:8px;overflow:hidden">{head}{chips}'
            f'<div style="max-height:520px;overflow:auto">{table}</div>'
            f'{_footer("Deterministic MRP-tree validator · read from MD04 · ~0 LLM tokens")}</div>')
    sub = f"{len(nodes)} nodes · {po}+{pr} planned · {data.get('verdict', '')}"
    return _wrap(f"MRP Tree {data.get('root', '')}", sub, body)
