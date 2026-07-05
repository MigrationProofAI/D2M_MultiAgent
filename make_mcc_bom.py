#!/usr/bin/env python
"""make_mcc_bom.py -- a REALISTIC 5-level-deep Schneider Electric product: a Motor Control Center (MCC)
lineup. This is the natural depth-5 showcase because that's literally how an MCC is engineered:

  FERT   MCC Lineup (the whole switchboard)
   L1    Vertical Section (structural bay)
    L2   Compartment / Bucket (drawout unit within the section)
     L3  Combination Starter Unit (disconnect + contactor + overload, as ONE assembly)
      L4 Contactor Assembly  /  Overload Relay Assembly   (a starter unit's own sub-builds)
       L5 (bought, leaf)      coil, main contacts, arc chute, springs, bimetal strip...

5 MADE tiers (FERT+L1+L2+L3+L4) before the bought leaves -- proves genesis's recursive depth handling
at real scale. Same two-sheet schema as the other fixtures (BOM + Operations).

  python make_mcc_bom.py --sections 3 --buckets 3 --out bom_mcc.xlsx
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server"))
BOM_COLS = ["id", "parent_id", "level", "role", "type", "name", "description",
            "material", "quantity", "unit", "vendor", "price", "plant"]
OP_COLS = ["node_id", "operation", "text", "work_center", "setup_time", "run_time"]

FERT_OPS = [("10", "Section Marriage", "ASSEMBLY", 45, 30), ("20", "Bus Splicing", "ASSEMBLY", 30, 20),
            ("30", "Meggar & HiPot Test", "PACK01", 25, 20), ("40", "Pack & Crate", "PACK01", 8, 10)]
SECTION_OPS = [("10", "Structural Assembly", "ASSEMBLY", 20, 15), ("20", "Bus Bar Install", "ASSEMBLY", 12, 10)]
BUCKET_OPS = [("10", "Compartment Assembly", "ASSEMBLY", 10, 8), ("20", "Door Fit", "ASSEMBLY", 6, 4)]
STARTER_OPS = [("10", "Unit Wiring", "ASSEMBLY", 12, 10), ("20", "Unit Test", "PACK01", 8, 6)]
CONTACTOR_OPS = [("10", "Contactor Build", "ASSEMBLY", 8, 6), ("20", "Contactor Test", "PACK01", 5, 4)]
RELAY_OPS = [("10", "Relay Build", "ASSEMBLY", 6, 5), ("20", "Relay Calibration", "PACK01", 5, 4)]

CONTACTOR_PARTS = [("Contactor Coil", "24V AC contactor coil", "HAWA", 1, 6.5),
                   ("Main Contact Set", "silver-alloy main contact set", "HAWA", 1, 8.2),
                   ("Arc Chute", "molded arc chute assembly", "ROH", 1, 4.8),
                   ("Contact Spring Set", "contact pressure spring set", "ROH", 1, 1.3),
                   ("Auxiliary Contact Block", "1NO/1NC auxiliary block", "HAWA", 1, 3.6)]
RELAY_PARTS = [("Bimetal Strip Set", "thermal bimetal strip set", "ROH", 1, 2.9),
              ("Overload Reset Lever", "manual reset lever", "ROH", 1, 1.1),
              ("Overload Trip Contact", "trip contact assembly", "HAWA", 1, 2.4),
              ("Overload Calibration Dial", "current-range calibration dial", "HAWA", 1, 1.8)]
STARTER_BOUGHT = [("Disconnect Switch", "3-pole rotary disconnect switch", "HAWA", 1, 14.0),
                  ("Control Power Transformer", "480:120V control transformer", "HAWA", 1, 22.0)]
BUCKET_BOUGHT = [("Bucket Door", "hinged compartment door", "ROH", 1, 9.5),
                 ("Door Hinge Set", "stainless hinge set", "HAWA", 1, 1.6),
                 ("Compartment Guide Rail", "drawout guide rail pair", "ROH", 1, 3.4)]
SECTION_BOUGHT = [("Horizontal Wireway", "top horizontal wireway", "ROH", 1, 11.0),
                  ("Vertical Wireway", "side vertical wireway", "ROH", 1, 9.0),
                  ("Ground Bus Bar", "section ground bus bar", "ROH", 1, 6.5)]
TOP_BOUGHT = [("Common Ground Bus", "lineup-length ground bus", "ROH", 1, 18.0),
             ("Lineup Nameplate", "laser-etched lineup nameplate", "HAWA", 1, 1.5),
             ("Anchoring Kit", "floor anchoring bolt kit", "ROH", 1, 4.0)]


def build(n_sections, n_buckets, vendor, plant):
    bom, ops = [], []

    def row(**kw):
        bom.append({c: kw.get(c, "") for c in BOM_COLS})

    def op(nid, o):
        for (num, text, wc, su, ru) in o:
            ops.append({"node_id": nid, "operation": num, "text": text,
                        "work_center": wc, "setup_time": su, "run_time": ru})

    def bought_rows(parent_id, level, parts, tag):
        for k, (pn, pd, pt, qty, pr) in enumerate(parts):
            row(id=f"{parent_id}{tag}{k}", parent_id=parent_id, level=level, role="bought", type=pt,
                name=pn, description=pd, quantity=qty, unit="EA", vendor=vendor, price=pr)

    row(id="P", parent_id="", level=0, role="parent", type="FERT",
        name=f"MCC Lineup - Model 6, {n_sections}-Section", description="Model 6 motor control center lineup",
        quantity=1, unit="EA", plant=plant)
    op("P", FERT_OPS)
    bought_rows("P", 1, TOP_BOUGHT, "T")

    for si in range(n_sections):
        sid = f"S{si}"
        row(id=sid, parent_id="P", level=1, role="made", type="HALB",
            name=f"Vertical Section {chr(65+si)}", description="NEMA 1 vertical section", quantity=1, unit="EA")
        op(sid, SECTION_OPS)
        bought_rows(sid, 2, SECTION_BOUGHT, "B")
        for bi in range(n_buckets):
            bid = f"{sid}K{bi}"
            row(id=bid, parent_id=sid, level=2, role="made", type="HALB",
                name=f"Bucket {si*n_buckets+bi+1}", description="drawout starter compartment", quantity=1, unit="EA")
            op(bid, BUCKET_OPS)
            bought_rows(bid, 3, BUCKET_BOUGHT, "B")
            uid = f"{bid}U"
            row(id=uid, parent_id=bid, level=3, role="made", type="HALB",
                name=f"Combination Starter Unit {si*n_buckets+bi+1}",
                description="disconnect + contactor + overload combination starter", quantity=1, unit="EA")
            op(uid, STARTER_OPS)
            bought_rows(uid, 4, STARTER_BOUGHT, "B")
            cid = f"{uid}C"
            row(id=cid, parent_id=uid, level=4, role="made", type="HALB",
                name="Contactor Assembly", description="motor contactor assembly", quantity=1, unit="EA")
            op(cid, CONTACTOR_OPS)
            bought_rows(cid, 5, CONTACTOR_PARTS, "P")
            rid = f"{uid}R"
            row(id=rid, parent_id=uid, level=4, role="made", type="HALB",
                name="Overload Relay Assembly", description="thermal overload relay assembly", quantity=1, unit="EA")
            op(rid, RELAY_OPS)
            bought_rows(rid, 5, RELAY_PARTS, "P")
    return bom, ops


def write_xlsx(path, bom_rows, op_rows):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook(); ws = wb.active; ws.title = "BOM"; ws.append(BOM_COLS)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in bom_rows:
        ws.append([r.get(col, "") for col in BOM_COLS])
    wo = wb.create_sheet("Operations"); wo.append(OP_COLS)
    for c in wo[1]:
        c.font = Font(bold=True)
    for r in op_rows:
        wo.append([r.get(col, "") for col in OP_COLS])
    wb.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sections", type=int, default=3)
    ap.add_argument("--buckets", type=int, default=3, help="buckets (starter units) per section")
    ap.add_argument("--out", default="bom_mcc.xlsx")
    ap.add_argument("--vendor", default="17300001")
    ap.add_argument("--plant", default=os.getenv("SAP_PLANT", "1710"))
    args = ap.parse_args()
    bom, ops = build(args.sections, args.buckets, args.vendor, args.plant)
    write_xlsx(args.out, bom, ops)
    from excel_bom import genesis_from_excel
    spec, warnings = genesis_from_excel(args.out)

    def walk(cs, made=0, bought=0, maxlvl=0, lvl=1):
        for c in cs:
            maxlvl = max(maxlvl, lvl)
            if c.get("role") == "made" or c.get("type") in ("HALB", "FERT"):
                made += 1
            else:
                bought += 1
            made, bought, maxlvl = walk(c.get("components", []), made, bought, maxlvl, lvl + 1)
        return made, bought, maxlvl
    m, b, d = walk(spec["components"])
    print(f"wrote {args.out}: {len(bom)} BOM rows, {len(ops)} ops rows")
    print(f"  1 FERT + {m} HALB + {b} bought = {1 + m + b} materials, max made-depth {d + 1} (FERT counted as depth 1)")
    for w in warnings[:8]:
        print(f"  WARN: {w}")


if __name__ == "__main__":
    main()
