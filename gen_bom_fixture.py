#!/usr/bin/env python
"""gen_bom_fixture.py -- emit a synthetic tabbed-Excel BOM of a target size for scale-testing genesis.

  python gen_bom_fixture.py --n 50  --out bom_50.xlsx     # 50 materials
  python gen_bom_fixture.py --n 200 --out bom_200.xlsx    # 200 materials
  python gen_bom_fixture.py --template --out bom_template.xlsx   # empty header-only workbook

Structure: 1 FERT root -> ~20% made HALB sub-assemblies (layer 1) -> bought raws (layer 2), plus some
top-level bought parts under the FERT. Vendors/prices on every bought row (so PIR+cost are created at all
levels), 2 routing ops on the FERT + each HALB. Deterministic (seeded), and self-validates via
excel_bom.genesis_from_excel before saving. Total material rows == --n exactly.
"""
import os
import sys
import argparse
import random

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server"))

BOM_COLS = ["id", "parent_id", "level", "role", "type", "name", "description",
            "material", "quantity", "unit", "vendor", "price", "plant"]
OP_COLS = ["node_id", "operation", "text", "work_center", "setup_time", "run_time"]
_VENDORS = ["V-ACME", "V-CELL", "V-MOTORS", "V-PROPS", "V-NAV", "V-FRAME", "V-BOLT", "V-EPOXY"]


def build_bom(n, seed=42, vendor="17300001"):
    """Return (bom_rows, op_rows) totalling exactly `n` material rows (1 FERT + HALBs + bought).
    `vendor` is used on every bought row (must be a REAL SAP supplier so PIR/cost commit)."""
    rng = random.Random(seed)
    bom, ops = [], []

    def row(**kw):
        bom.append({c: kw.get(c, "") for c in BOM_COLS})

    def op(node_id, o, text, wc, su, ru):
        ops.append({"node_id": node_id, "operation": o, "text": text,
                    "work_center": wc, "setup_time": su, "run_time": ru})

    row(id="P", parent_id="", level=0, role="parent", type="FERT",
        name="Assembly", description=f"Test Assembly {n}p", quantity=1, unit="EA", plant="1710")
    op("P", "10", "Final Assembly", "ASSEMBLY", 30, 10)
    op("P", "20", "Packaging", "PACK01", 5, 2)

    remaining = n - 1
    H = min(remaining, max(1, round(remaining * 0.20)))     # ~20% made HALBs
    bought = remaining - H
    raws_total = int(bought * 0.7)                          # 70% of bought sit under HALBs as raws
    top_total = bought - raws_total                         # rest are top-level bought under the FERT

    per = [raws_total // H] * H if H else []
    for i in range(raws_total % H if H else 0):
        per[i] += 1

    for i in range(H):
        hid = f"A{i}"
        row(id=hid, parent_id="P", level=1, role="made", type="HALB",
            name=f"SubAsm{i}", description=f"Sub-Assembly {i}", quantity=rng.choice([1, 1, 2, 4]), unit="EA")
        op(hid, "10", "Assemble", "ASSEMBLY", 20, 5)
        op(hid, "20", "Test", "PACK01", 5, 3)
        for j in range(per[i]):
            row(id=f"{hid}R{j}", parent_id=hid, level=2, role="bought", type=rng.choice(["ROH", "HAWA"]),
                name=f"Raw{i}_{j}", description=f"Raw part {i}-{j}", quantity=rng.choice([1, 1, 2, 4]),
                unit="EA", vendor=vendor, price=round(rng.uniform(0.5, 45), 2))

    for k in range(top_total):
        row(id=f"B{k}", parent_id="P", level=1, role="bought", type=rng.choice(["HAWA", "ROH"]),
            name=f"Buy{k}", description=f"Bought part {k}", quantity=rng.choice([1, 1, 2]),
            unit="EA", vendor=vendor, price=round(rng.uniform(1, 50), 2))

    return bom, ops


def write_xlsx(path, bom_rows, op_rows):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = "BOM"
    ws.append(BOM_COLS)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in bom_rows:
        ws.append([r.get(col, "") for col in BOM_COLS])
    wo = wb.create_sheet("Operations")
    wo.append(OP_COLS)
    for c in wo[1]:
        c.font = Font(bold=True)
    for r in op_rows:
        wo.append([r.get(col, "") for col in OP_COLS])
    wb.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50, help="total material rows (1 FERT + HALBs + bought)")
    ap.add_argument("--out", default="bom.xlsx")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--vendor", default="17300001", help="real SAP supplier for all bought rows")
    ap.add_argument("--template", action="store_true", help="write an empty header-only workbook")
    args = ap.parse_args()

    if args.template:
        write_xlsx(args.out, [], [])
        print(f"wrote empty template -> {args.out}")
        return

    bom, ops = build_bom(args.n, args.seed, args.vendor)
    write_xlsx(args.out, bom, ops)
    # self-validate: parse it back
    from excel_bom import genesis_from_excel
    spec, warnings = genesis_from_excel(args.out)
    n_mat = 1 + len(spec["components"]) + sum(len(c.get("components", [])) for c in spec["components"])
    print(f"wrote {args.out}: {len(bom)} BOM rows, {len(ops)} ops rows  (parsed spec: {n_mat} materials)")
    for w in warnings[:5]:
        print(f"  WARN: {w}")


if __name__ == "__main__":
    main()
