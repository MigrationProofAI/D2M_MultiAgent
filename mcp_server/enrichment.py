"""enrichment.py -- OPT-IN web-sourcing pass for the file-genesis path.

The deterministic Excel path uses whatever sourcing the file already carries -- that is by design (lossless,
reproducible, ~0 tokens), which is why scale tests run on it. But for a REAL design where prices are BLANK,
this pass fills them from the web (Serper/Google) BEFORE commit -- the "it found the price" behaviour of the
image genesis, bolted onto the lossless file path and OFF by default so scale benchmarks stay deterministic.

Scope (v1): PRICE only -- a number SAP can use directly as a cost-condition rate. The vendor stays as the
file's SAP vendor NUMBER; mapping a web vendor NAME to a SAP vendor master is a separate lookup, deferred.
Deterministic (regex extraction, no LLM) and parallel, so even opt-in it costs ~0 model tokens -- only web
calls. Reads nothing from SAP and mutates only blank prices in the spec, so it can never corrupt real data."""
import os
import re
import concurrent.futures

import requests

_SERPER_URL = "https://google.serper.dev/search"
_WORKERS = int(os.getenv("ENRICH_WORKERS", "8"))
# a currency amount: "$12.50", "US$ 8", "5.00 USD", "3.20 each"
_PRICE = re.compile(r"(?:US)?\$\s*([0-9][0-9,]*\.?[0-9]{0,2})"
                    r"|([0-9][0-9,]*\.[0-9]{2})\s*(?:USD|EUR|GBP|each|/\s*ea)\b", re.I)


def _search(query):
    key = os.getenv("SERPER_API_KEY")
    if not key:
        return ""
    try:
        r = requests.post(_SERPER_URL, headers={"X-API-KEY": key, "Content-Type": "application/json"},
                          json={"q": query, "num": 5}, timeout=30)
        r.raise_for_status()
        d = r.json()
    except Exception:
        return ""
    parts = []
    ab = d.get("answerBox", {}) or {}
    if ab.get("answer") or ab.get("snippet"):
        parts.append(ab.get("answer") or ab.get("snippet"))
    for o in (d.get("organic", []) or [])[:5]:
        parts.append(f"{o.get('title', '')} {o.get('snippet', '')}")
    return "  ".join(parts)


def _extract_price(text):
    """A representative unit price from search text: the MEDIAN of plausible amounts (robust to one outlier
    like a bulk/reel price). None if nothing sane is found -- never guess."""
    vals = []
    for m in _PRICE.finditer(text or ""):
        raw = m.group(1) or m.group(2)
        if raw:
            try:
                vals.append(float(raw.replace(",", "")))
            except ValueError:
                pass
    vals = sorted(v for v in vals if 0.01 <= v <= 100000)     # drop obvious nonsense
    return round(vals[len(vals) // 2], 2) if vals else None


def _bought_missing_price(spec):
    """Every bought node in the spec tree whose price is blank (None / '' / 0) -- the enrichment targets."""
    out = []

    def walk(n):
        for c in (n.get("components") or []):
            if c.get("role") == "bought" and c.get("price") in (None, "", 0, 0.0):
                out.append(c)
            walk(c)
    walk(spec)
    return out


def enrich_sourcing(spec, on_step=None):
    """Fill blank prices on bought nodes from the web, in place. Returns (spec, notes). Never raises; a search
    or key failure just leaves the price blank and says so -- honest, like the verifiers."""
    def emit(msg):
        if on_step:
            try:
                on_step({"kind": "reasoning", "text": msg})
            except Exception:
                pass

    targets = _bought_missing_price(spec)
    if not targets:
        return spec, ["enrichment: every bought part already has a price -- nothing to source."]
    if not os.getenv("SERPER_API_KEY"):
        return spec, [f"enrichment SKIPPED: {len(targets)} part(s) have no price, but SERPER_API_KEY is not "
                      f"set -- no web sourcing available."]
    emit(f"web-sourcing prices for {len(targets)} bought part(s) with no price · {_WORKERS} parallel…")

    def _one(node):
        q = f"{node.get('description') or node.get('name')} unit price supplier"
        return node, _extract_price(_search(q))

    notes, filled = [], 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        for node, price in pool.map(_one, targets):
            label = f"{node.get('name')} ({node.get('description')})"
            if price is not None:
                node["price"] = price
                filled += 1
                notes.append(f"  {label}: sourced ${price}")
            else:
                notes.append(f"  {label}: no price found on the web (left blank)")
    emit(f"enrichment: filled {filled}/{len(targets)} price(s) from the web")
    notes.insert(0, f"web-sourced pricing (opt-in): filled {filled}/{len(targets)} missing price(s).")
    return spec, notes
