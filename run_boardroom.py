"""THE BOARDROOM, live — convene the cross-functional panel on a master-data proposal and watch the
five function personas review it CONCURRENTLY, then the Chair synthesise one board decision.

This is the 'boardroom with personas across functions' from STARTING_POINT.md — the parallel + hybrid
shapes, with real engineering/procurement/compliance/finance/planning lenses. Pure-reasoning review
(no SAP writes); every member has read+advise/veto authority only.

Run from conda base:
    $env:MODEL_PROVIDER = "anthropic"
    python run_boardroom.py
"""
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from boardroom import convene_board, PERSONAS

# A deliberately IMPERFECT proposal so each function has something real to catch.
PROPOSAL = """PROPOSAL — new finished good 'SKATE-100' (skateboard) for plant 1710.
Structure:
- FERT: Skateboard (1)
  - Board/Deck (HAWA, bought, 1) — vendor not yet decided, no price
  - Trucks (HAWA, bought, 2) — vendor 17300001, price $18
  - Wheel Assembly (HALB, made, 4) — its own BOM: Tire (1), Rim (1), Bearing screws (4)
  - Deck screws (HAWA, bought, 8) — vendor 17300001, price $0.01 (placeholder)
Master data so far:
- All materials created; CountryOfOrigin left BLANK on every material.
- FERT Skateboard: routing created, production version 0001 created.
- Wheel Assembly (HALB): BOM created, but NO routing and NO production version yet.
- HAWA prices: only Trucks priced; Deck/Board has no PIR; Deck screws PIR = $0.01.
- Standard cost: not yet released for the FERT or the HALB.
- MRP type PD on the FERT; no MRP controller set.
Question for the board: is this ready to release to production, or what must change first?"""


def main():
    print("=" * 80)
    print("D2M BOARDROOM  —  5 functional personas review CONCURRENTLY, then the Chair decides")
    print("=" * 80)
    print("Members:", " · ".join(f"{PERSONAS[m][0]} {m}" for m in PERSONAS))

    t0 = time.time()
    out = convene_board(PROPOSAL)            # parallel reviews + synthesised decision
    dt = time.time() - t0

    for m in out["members"]:
        print("\n" + "-" * 80)
        print(f"{PERSONAS[m][0]}  {m.upper()} review")
        print("-" * 80)
        print(out["reviews"][m].strip())

    print("\n" + "=" * 80)
    print("🪑  CHAIR — synthesised board decision")
    print("=" * 80)
    print(out["verdict"].strip())

    print("\n" + "=" * 80)
    print(f"{len(out['members'])} functions reviewed concurrently + Chair synthesis in {dt:.1f}s.")
    print("Each is a bounded agent (its own memory, read+advise only). Add a function = one PERSONAS entry.")
    print("=" * 80)


if __name__ == "__main__":
    main()
