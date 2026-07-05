#!/usr/bin/env python
"""make_realistic_bom.py -- author a REALISTIC, hand-curated tabbed-Excel BOM (not synthetic).

A Class-1 urban e-bike: 1 FERT -> 15 made HALB sub-assemblies -> real bought parts (ROH/HAWA),
plus a few top-level bought consumables. ~113 materials total, so previews read like a real product
instead of SubAsm0/Raw0_0. Same two-sheet schema as gen_bom_fixture (BOM + Operations), so it parses
through excel_bom.genesis_from_excel unchanged. Vendors default to the one known-real supplier
(17300001); swap in a richer vendor list later.

  python make_realistic_bom.py --out bom_ebike.xlsx
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server"))

BOM_COLS = ["id", "parent_id", "level", "role", "type", "name", "description",
            "material", "quantity", "unit", "vendor", "price", "plant"]
OP_COLS = ["node_id", "operation", "text", "work_center", "setup_time", "run_time"]

FERT = ("E-Bike UrbanCruiser E1", "Class-1 urban e-bike, 250W mid-drive",
        [("10", "Sub-assembly Marriage", "ASSEMBLY", 40, 25),
         ("20", "Cable Routing & Loom", "ASSEMBLY", 15, 12),
         ("30", "Final QC & Road Test", "PACK01", 10, 8),
         ("40", "Pack & Crate", "PACK01", 5, 6)])

# each: (halb_name, halb_desc, [ops], [ (part_name, part_desc, type, qty, price) ... ])
SUBS = [
 ("Frame Assembly", "Welded 6061-T6 aluminium frame",
  [("10", "Tube Prep & Mitre", "ASSEMBLY", 20, 8), ("20", "TIG Frame Weld", "ASSEMBLY", 30, 15), ("30", "Paint & Cure", "PACK01", 15, 20)],
  [("Down Tube", "6061-T6 aluminium down tube", "ROH", 1, 18.50),
   ("Top Tube", "6061-T6 aluminium top tube", "ROH", 1, 14.20),
   ("Head Tube", "CNC head tube", "ROH", 1, 9.80),
   ("Seat Tube", "6061-T6 aluminium seat tube", "ROH", 1, 12.40),
   ("Chainstay Pair", "Formed chainstay pair", "ROH", 1, 16.75),
   ("Seatstay Pair", "Formed seatstay pair", "ROH", 1, 13.30),
   ("Dropout Set", "Forged rear dropout set", "ROH", 1, 7.90),
   ("Frame Weld Kit", "Filler + gusset weld kit", "ROH", 1, 4.60),
   ("Head Badge", "Anodised head badge", "HAWA", 1, 2.10)]),
 ("Front Wheel Assembly", "Laced & trued front wheel",
  [("10", "Wheel Lacing", "ASSEMBLY", 12, 10), ("20", "Truing", "ASSEMBLY", 8, 6), ("30", "Tire Mount", "PACK01", 5, 4)],
  [("Front Rim", "28in double-wall alloy rim", "HAWA", 1, 22.00),
   ("Front Hub", "Sealed-bearing front hub", "HAWA", 1, 18.90),
   ("Front Spoke Set", "Stainless spoke set 32H", "ROH", 1, 8.40),
   ("Nipple Set Front", "Brass nipple set 32H", "ROH", 1, 2.30),
   ("Front Tire", "28in puncture-guard tire", "HAWA", 1, 26.50),
   ("Front Inner Tube", "28in Schrader inner tube", "HAWA", 1, 5.20),
   ("Rim Tape Front", "High-pressure rim tape", "ROH", 1, 1.40),
   ("QR Skewer Front", "Quick-release skewer", "HAWA", 1, 3.60)]),
 ("Rear Wheel Assembly", "Laced & trued rear wheel",
  [("10", "Wheel Lacing", "ASSEMBLY", 12, 10), ("20", "Truing", "ASSEMBLY", 8, 6), ("30", "Tire Mount", "PACK01", 5, 4)],
  [("Rear Rim", "28in double-wall alloy rim", "HAWA", 1, 22.00),
   ("Rear Hub Cassette", "Cassette rear hub 11s", "HAWA", 1, 29.80),
   ("Rear Spoke Set", "Stainless spoke set 32H", "ROH", 1, 8.40),
   ("Nipple Set Rear", "Brass nipple set 32H", "ROH", 1, 2.30),
   ("Rear Tire", "28in puncture-guard tire", "HAWA", 1, 26.50),
   ("Rear Inner Tube", "28in Schrader inner tube", "HAWA", 1, 5.20),
   ("Rim Tape Rear", "High-pressure rim tape", "ROH", 1, 1.40),
   ("Cassette 11spd", "11-42T 11-speed cassette", "HAWA", 1, 34.00)]),
 ("Mid-Drive Motor Assembly", "250W mid-drive motor unit",
  [("10", "Stator Winding", "ASSEMBLY", 25, 18), ("20", "Motor Assembly", "ASSEMBLY", 20, 14), ("30", "Dyno Bench Test", "PACK01", 12, 10)],
  [("Motor Stator", "Laminated stator core", "ROH", 1, 42.00),
   ("Motor Rotor", "Bonded-magnet rotor", "ROH", 1, 38.50),
   ("Motor Housing", "Die-cast alloy housing", "ROH", 1, 24.00),
   ("Torque Sensor", "Bottom-bracket torque sensor", "HAWA", 1, 31.00),
   ("Motor Ctrl Board", "FOC motor controller PCBA", "HAWA", 1, 46.00),
   ("Motor Harness", "Motor phase + hall harness", "ROH", 1, 6.80),
   ("Motor Mount Bolts", "M6 motor mount bolt set", "ROH", 6, 0.45)]),
 ("Battery Pack Assembly", "36V 14Ah 21700 battery pack",
  [("10", "Cell Sort & Match", "ASSEMBLY", 18, 12), ("20", "Spot-Weld Pack", "ASSEMBLY", 22, 16), ("30", "Pack Burn-in Test", "PACK01", 15, 20)],
  [("Li-ion Cell 21700", "21700 Li-ion cell 5000mAh", "HAWA", 40, 3.80),
   ("Cell Holder", "40-cell PC holder frame", "ROH", 1, 6.50),
   ("BMS Board", "10S smart BMS board", "HAWA", 1, 28.00),
   ("Battery Housing", "ABS battery housing shell", "ROH", 1, 14.00),
   ("Battery Connector", "XT60 power connector", "HAWA", 2, 1.30),
   ("Battery Lock", "Keyed battery lock latch", "HAWA", 1, 7.40),
   ("Charge Port", "3-pin charge port assy", "HAWA", 1, 4.20)]),
 ("Drivetrain Assembly", "11-speed drivetrain",
  [("10", "Crank & BB Fit", "ASSEMBLY", 14, 10), ("20", "Chain Route & Index", "ASSEMBLY", 12, 9)],
  [("Crank Arm Set", "Forged alloy crank arm set", "HAWA", 1, 27.00),
   ("Chainring 42T", "42T narrow-wide chainring", "HAWA", 1, 15.50),
   ("Chain", "11-speed roller chain", "HAWA", 1, 18.00),
   ("Rear Derailleur", "11-speed rear derailleur", "HAWA", 1, 38.00),
   ("Shifter", "11-speed trigger shifter", "HAWA", 1, 22.00),
   ("Derailleur Cable", "Stainless shift cable + housing", "ROH", 1, 3.40),
   ("Bottom Bracket", "Threaded sealed BB", "HAWA", 1, 12.00),
   ("Pedal Set", "Alloy platform pedal set", "HAWA", 1, 9.50)]),
 ("Front Brake Assembly", "Hydraulic front disc brake",
  [("10", "Hose Cut & Fit", "ASSEMBLY", 10, 7), ("20", "Bleed & Test", "PACK01", 12, 8)],
  [("Front Caliper", "2-piston hydraulic caliper", "HAWA", 1, 24.00),
   ("Front Rotor 180", "180mm 6-bolt disc rotor", "HAWA", 1, 8.90),
   ("Front Brake Pads", "Sintered disc pad pair", "HAWA", 1, 6.50),
   ("Front Brake Lever", "Hydraulic brake lever", "HAWA", 1, 16.00),
   ("Front Hose", "Kevlar hydraulic hose", "ROH", 1, 4.80),
   ("Brake Fluid DOT", "DOT 5.1 brake fluid 100ml", "HAWA", 1, 3.20)]),
 ("Rear Brake Assembly", "Hydraulic rear disc brake",
  [("10", "Hose Cut & Fit", "ASSEMBLY", 10, 7), ("20", "Bleed & Test", "PACK01", 12, 8)],
  [("Rear Caliper", "2-piston hydraulic caliper", "HAWA", 1, 24.00),
   ("Rear Rotor 160", "160mm 6-bolt disc rotor", "HAWA", 1, 8.40),
   ("Rear Brake Pads", "Sintered disc pad pair", "HAWA", 1, 6.50),
   ("Rear Brake Lever", "Hydraulic brake lever", "HAWA", 1, 16.00),
   ("Rear Hose", "Kevlar hydraulic hose", "ROH", 1, 5.60)]),
 ("Cockpit Assembly", "Handlebar & steering cockpit",
  [("10", "Bar & Stem Fit", "ASSEMBLY", 8, 6), ("20", "Torque & Align", "ASSEMBLY", 6, 5)],
  [("Handlebar", "Alloy riser handlebar", "HAWA", 1, 14.00),
   ("Stem", "Adjustable alloy stem", "HAWA", 1, 11.00),
   ("Grips Pair", "Ergonomic lock-on grips", "HAWA", 1, 7.80),
   ("Headset", "Sealed threadless headset", "HAWA", 1, 9.20),
   ("Bar End Plugs", "Alloy bar end plug set", "ROH", 1, 1.10)]),
 ("Seat Assembly", "Saddle & seatpost",
  [("10", "Post & Clamp Fit", "ASSEMBLY", 6, 4)],
  [("Saddle", "Gel comfort saddle", "HAWA", 1, 15.00),
   ("Seatpost", "Alloy 31.6mm seatpost", "HAWA", 1, 10.50),
   ("Seat Clamp", "QR seatpost clamp", "HAWA", 1, 4.30),
   ("Suspension Insert", "Elastomer suspension insert", "ROH", 1, 6.90)]),
 ("Fork Assembly", "Suspension front fork",
  [("10", "Fork Build", "ASSEMBLY", 16, 12), ("20", "Oil Fill & Seal", "PACK01", 10, 8)],
  [("Fork Lowers", "Magnesium fork lowers", "ROH", 1, 28.00),
   ("Fork Stanchions", "Anodised stanchion pair", "ROH", 1, 22.00),
   ("Fork Crown", "Forged fork crown", "ROH", 1, 12.00),
   ("Fork Seal Kit", "Dust + oil seal kit", "HAWA", 1, 6.40),
   ("Fork Damper", "Hydraulic damper cartridge", "HAWA", 1, 34.00)]),
 ("Lighting Harness", "Integrated lighting loom",
  [("10", "Loom Build & Test", "ASSEMBLY", 12, 9)],
  [("Front LED Light", "60-lux front LED headlight", "HAWA", 1, 12.50),
   ("Rear LED Light", "Brake-sense rear LED light", "HAWA", 1, 8.00),
   ("Wiring Loom", "Main lighting wiring loom", "ROH", 1, 5.40),
   ("Light Switch", "Bar-mount light switch", "HAWA", 1, 3.90),
   ("Reflector Set", "CPSC reflector set", "HAWA", 1, 2.60)]),
 ("Display & Control", "LCD display & remote",
  [("10", "Bracket Fit", "ASSEMBLY", 6, 4), ("20", "Firmware Flash", "PACK01", 8, 6)],
  [("LCD Display", "Backlit LCD e-bike display", "HAWA", 1, 45.00),
   ("Handlebar Remote", "5-button handlebar remote", "HAWA", 1, 12.00),
   ("Display Bracket", "Alloy display bracket", "ROH", 1, 3.20),
   ("Display Cable", "Display-to-controller cable", "ROH", 1, 2.80)]),
 ("Fender & Rack Assembly", "Fenders, rack & stand",
  [("10", "Fender & Rack Fit", "ASSEMBLY", 12, 9)],
  [("Front Fender", "Full-cover front fender", "HAWA", 1, 8.50),
   ("Rear Fender", "Full-cover rear fender", "HAWA", 1, 9.00),
   ("Rear Rack", "Alloy pannier rear rack", "HAWA", 1, 18.00),
   ("Rack Bolt Set", "M5 rack mounting bolt set", "ROH", 1, 2.20),
   ("Kickstand", "Adjustable side kickstand", "HAWA", 1, 7.60)]),
 ("Accessory Kit", "Rider accessory kit",
  [("10", "Kit Pack", "PACK01", 6, 4)],
  [("Bell", "Alloy ping bell", "HAWA", 1, 3.10),
   ("Bottle Cage", "Alloy bottle cage", "HAWA", 1, 4.50),
   ("Phone Mount", "Quad-lock phone mount", "HAWA", 1, 11.00),
   ("Mudguard Flap", "Rubber mudguard flap", "ROH", 1, 1.80)]),
]

TOP_BOUGHT = [
 ("Frame Bolt Kit", "M5/M6 stainless bolt kit", "ROH", 1, 6.20),
 ("Cable Housing Set", "Full cable + housing set", "ROH", 1, 5.40),
 ("Grip Tape", "Non-slip grip tape roll", "ROH", 1, 2.10),
 ("Owner Manual", "Printed owner + safety manual", "HAWA", 1, 1.50),
 ("Assembly Grease", "Anti-seize assembly grease", "ROH", 1, 3.80),
 ("Serial Plate", "Laser-etched serial plate", "ROH", 1, 1.20),
 ("Torque Sticker Set", "Torque-spec sticker set", "ROH", 1, 0.90),
]


def build(vendor, plant):
    bom, ops = [], []

    def row(**kw):
        bom.append({c: kw.get(c, "") for c in BOM_COLS})

    def op(node_id, o):
        for (num, text, wc, su, ru) in o:
            ops.append({"node_id": node_id, "operation": num, "text": text,
                        "work_center": wc, "setup_time": su, "run_time": ru})

    row(id="P", parent_id="", level=0, role="parent", type="FERT",
        name=FERT[0], description=FERT[1], quantity=1, unit="EA", plant=plant)
    op("P", FERT[2])
    for i, (hname, hdesc, hops, parts) in enumerate(SUBS):
        hid = f"A{i}"
        row(id=hid, parent_id="P", level=1, role="made", type="HALB",
            name=hname, description=hdesc, quantity=1, unit="EA")
        op(hid, hops)
        for j, (pn, pd, pt, qty, price) in enumerate(parts):
            row(id=f"{hid}R{j}", parent_id=hid, level=2, role="bought", type=pt,
                name=pn, description=pd, quantity=qty, unit="EA", vendor=vendor, price=price)
    for k, (pn, pd, pt, qty, price) in enumerate(TOP_BOUGHT):
        row(id=f"B{k}", parent_id="P", level=1, role="bought", type=pt,
            name=pn, description=pd, quantity=qty, unit="EA", vendor=vendor, price=price)
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
    ap.add_argument("--out", default="bom_ebike.xlsx")
    ap.add_argument("--vendor", default="17300001")
    ap.add_argument("--plant", default=os.getenv("SAP_PLANT", "1710"))
    args = ap.parse_args()

    bom, ops = build(args.vendor, args.plant)
    write_xlsx(args.out, bom, ops)
    from excel_bom import genesis_from_excel
    spec, warnings = genesis_from_excel(args.out)
    n = 1 + len(spec["components"]) + sum(len(c.get("components", [])) for c in spec["components"])
    print(f"wrote {args.out}: {len(bom)} BOM rows, {len(ops)} ops rows  (parsed spec: {n} materials)")
    for w in warnings[:8]:
        print(f"  WARN: {w}")


if __name__ == "__main__":
    main()
