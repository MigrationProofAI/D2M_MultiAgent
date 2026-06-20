"""
codebook_extract.py — DEPLOYMENT-TIME tool. Run ONCE per SAP system at onboarding.

Builds code_book.json: for the coded material fields you care about, the allowed
codes and their language texts, read straight from SAP's check/text tables.

Clean-core: it ONLY calls the standard RFC_READ_TABLE (no custom ABAP object).
  1. RFC_READ_TABLE on DD03L   -> each base table's fields + check tables + data elements
  2. skip "check tables" that are master/transaction data (DD02L delivery class)
  3. RFC_READ_TABLE on each real check table + its text table -> codes + texts
  4. fields with NO check table: read DOMAIN fixed values (DD04L -> DD07L) -> codes + texts
  5. capture each value list's scoping key fields (relations, e.g. storage loc by plant)
  6. apply FIELD_BRIDGE (OData field -> DB field) -> the agent-ready section

The running agent never needs RFC: it reads the static code_book.json this produces.

Requirements / caveats
  - pip install pyrfc   (needs the SAP NetWeaver RFC SDK on the machine)
  - RFC creds come from SAP_RFC_* in .env (fall back to the SAP_* HTTP creds)
  - The RFC user must be allowed to call RFC_READ_TABLE (S_RFC) and read these
    tables (S_TABU_*). Some hardened systems restrict RFC_READ_TABLE.
  - SAP language is the 1-char code ('E'), NOT the 2-char ISO ('EN'). Set SAP_SPRAS.
  - RFC_READ_TABLE forbids the client field (MANDT) in the WHERE -- it always
    runs in your logon client -- so we never filter on it.
"""
import datetime
import json
import os
import re

from dotenv import load_dotenv

try:
    from pyrfc import Connection
except ImportError:
    raise SystemExit(
        "pyrfc not installed. Run `pip install pyrfc` "
        "(requires the SAP NetWeaver RFC SDK to be installed and on PATH)."
    )

load_dotenv()

# ----------------------------- CONFIG ---------------------------------------
# Material-master tables to scan for coded fields. Add more as you need them
# (each is a material view: general / plant-MRP / sales / UoM / EAN / valuation / storage).
BASE_TABLES = ["MARA", "MARC", "MVKE", "MARM", "MEAN", "MBEW", "MARD"]

# The bridge: the name the AGENT uses (OData/CDS field, from API_PRODUCT_SRV's
# A_Product + child entities)  ->  the DB field that backs it. The check table /
# domain is DISCOVERED from the DDIC, never hardcoded. Expand this freely: every
# entry whose DB field carries a value list becomes agent-queryable BY NAME (this
# is what was missing -- only 5 fields were bridged, so the agent "couldn't find"
# Plant et al. even though the values were in the catalog).
FIELD_BRIDGE = {
    # --- Basic data (MARA / A_Product) ---
    "ProductType":                "MTART",      # -> T134
    "IndustrySector":             "MBRSH",      # -> T137
    "ProductGroup":               "MATKL",      # -> T023  ("Material Group")
    "BaseUnit":                   "MEINS",      # -> T006
    "CrossPlantStatus":           "MSTAE",      # -> T141
    "Division":                   "SPART",      # -> TSPA
    "ProductHierarchy":           "PRDHA",      # -> T179
    "WeightUnit":                 "GEWEI",      # -> T006
    "VolumeUnit":                 "VOLEH",      # -> T006
    "ItemCategoryGroup":          "MTPOS_MARA", # general item-category group
    "PurchaseOrderQuantityUnit":  "BSTME",      # -> T006
    "TransportationGroup":        "TRAGR",      # -> T173
    "WarehouseProductGroup":      "WHMATGR",
    "WarehouseStorageCondition":  "RAUBE",      # storage conditions
    "TemperatureConditionInd":    "TEMPB",      # temperature condition
    "QualityInspectionGroup":     "QGRP",
    "DangerousGoodsProfile":      "PROFL",
    "Brand":                      "BRAND_ID",
    # --- Plant / MRP / procurement (MARC / A_ProductPlant) ---
    "Plant":                      "WERKS",      # -> T001W
    "PurchasingGroup":            "EKGRP",      # -> T024
    "MRPType":                    "DISMM",      # -> T438A
    "MRPController":              "DISPO",      # -> T024D
    "MRPGroup":                   "DISGR",
    "ABCIndicator":               "MAABC",
    "ProcurementType":            "BESKZ",      # domain fixed values (E/F/X)
    "SpecialProcurementType":     "SOBSL",
    "LotSizingProcedure":         "DISLS",      # -> T439A
    "AvailabilityCheckType":      "MTVFP",      # -> TMVF
    "PlantSpecificMaterialStatus":"MMSTA",      # -> T141
    "MaterialFreightGroup":       "MFRGR",
    "ProductionSupervisor":       "FEVOR",      # -> T024F
    "ProductionSchedulingProfile":"SFCPF",
    "FiscalYearVariant":          "PERIV",      # -> T009
    "LoadingGroup":               "LADGR",      # -> TLGR
    "PeriodIndicator":            "PERKZ",      # domain fixed values
    "CommodityCode":              "STEUC",
    "SerialNumberProfile":        "SERNP",
    # --- Valuation / accounting (MBEW / A_ProductValuation) ---
    "ValuationClass":             "BKLAS",      # -> T025
    "ValuationCategory":          "BWTTY",      # -> T149
    "PriceControl":               "VPRSV",      # domain fixed values (S/V)
    # --- Sales (MVKE / A_ProductSalesDelivery) ---
    "ProductDistributionChnl":    "VTWEG",      # -> TVTW
    "SalesItemCategoryGroup":     "MTPOS",      # sales item-category group
    "ProductSalesStatus":         "VMSTA",      # -> T141
    "AccountDetnProductGroup":    "KTGRM",      # -> T157E
    "ProductCommissionGroup":     "PROVG",
    "SalesMeasureUnit":           "VRKME",      # -> T006
    "MaterialPricingGroup":       "KONDM",
    # --- Units of measure (MARM / A_ProductUnitOfMeasure) ---
    "AlternativeUnit":            "MEINH",      # -> T006
}

# Special cases where the "<table>T" text-table convention is WRONG.
# value = (text_table, code_field, text_field)
TEXT_TABLE_OVERRIDES = {
    "T006": ("T006A", "MSEH3", "MSEHT"),   # units: texts live in T006A, not T006T
}

# Delivery classes to SKIP: 'A' = master/transaction data (MARA, LFA1...),
# 'L' = transactional. Real config/check tables are 'C'/'E'/'G'/'S'.
# This is what stops MATNR's "check table" MARA dragging in every material.
SKIP_DELIVERY_CLASS = {"A", "L"}

# Real coded enumerations are small. Anything bigger is a repository
# (e.g. STXFADM smartforms), not a value list -- drop it. 500 keeps countries (255).
MAX_VALUES = 500

OUT_PATH = "code_book.json"
# SAP internal language is 1-char ('E' for English), NOT the 2-char ISO 'EN'.
SPRAS = os.getenv("SAP_SPRAS", "E")

# --------------------------- CONNECTION -------------------------------------
def connect() -> Connection:
    """RFC connection params (NOT the HTTPS ones). sysnr '00' matches this appliance."""
    return Connection(
        ashost=os.getenv("SAP_RFC_HOST") or os.getenv("SAP_HOST"),
        sysnr=os.getenv("SAP_SYSNR", "00"),
        client=os.getenv("SAP_CLIENT", "100"),
        user=os.getenv("SAP_RFC_USER") or os.getenv("SAP_USER"),
        passwd=os.getenv("SAP_RFC_PASSWORD") or os.getenv("SAP_PASS"),
        lang=os.getenv("SAP_LANG", "EN"),
    )

# ----------------------- RFC_READ_TABLE helper ------------------------------
def _where_lines(where):
    """RFC_READ_TABLE OPTIONS: each line must be <= 72 characters."""
    if not where:
        return []
    out, line = [], ""
    for tok in where.split(" "):
        if len(line) + len(tok) + 1 > 72:
            out.append({"TEXT": line})
            line = tok
        else:
            line = f"{line} {tok}".strip()
    if line:
        out.append({"TEXT": line})
    return out


def read_table(conn, table, fields, where=None, rowcount=0):
    """Read `fields` from `table`; return list[dict].

    Parses by OFFSET/LENGTH with DELIMITER='' so a separator inside a text value
    can never corrupt the column split (the classic RFC_READ_TABLE trap).
    Never put MANDT in `where` -- RFC_READ_TABLE rejects the client field.
    """
    res = conn.call(
        "RFC_READ_TABLE",
        QUERY_TABLE=table,
        DELIMITER="",
        FIELDS=[{"FIELDNAME": f} for f in fields],
        OPTIONS=_where_lines(where),
        ROWCOUNT=rowcount,
    )
    cols = res["FIELDS"]
    rows = []
    for d in res["DATA"]:
        wa = d["WA"]
        rows.append({
            c["FIELDNAME"]: wa[int(c["OFFSET"]):int(c["OFFSET"]) + int(c["LENGTH"])].strip()
            for c in cols
        })
    return rows

# ------------------------------ DDIC ----------------------------------------
_VALID_TABLE = re.compile(r"^[A-Z0-9/_]+$")


def field_catalog(conn, table):
    """All real fields of `table` from DD03L (name, key flag, check table, data
    element + type/length -- the last three drive the domain-value fallback)."""
    rows = read_table(conn, "DD03L",
                      ["FIELDNAME", "KEYFLAG", "CHECKTABLE", "ROLLNAME", "DATATYPE", "LENG"],
                      where=f"TABNAME = '{table}'")
    return [r for r in rows if r["FIELDNAME"] and not r["FIELDNAME"].startswith(".")]


def delivery_class(conn, table):
    """DD02L delivery class (CONTFLAG). Used to skip master/transaction tables
    (class 'A'/'L') so MATNR -> MARA etc. don't get treated as coded values."""
    rows = read_table(conn, "DD02L", ["CONTFLAG"], where=f"TABNAME = '{table}'")
    return rows[0]["CONTFLAG"] if rows else ""


def _non_client_key(cat):
    """Key fields of a table excluding MANDT/SPRAS (the code field lives here)."""
    return [r["FIELDNAME"] for r in cat
            if r["KEYFLAG"] == "X" and r["FIELDNAME"] not in ("MANDT", "SPRAS")]


def text_table_of(conn, check_table):
    """Locate a check table's text table. Honors TEXT_TABLE_OVERRIDES first, then
    the convention (CT + 'T'). Returns (table, code_field, text_field) or None.
    """
    if check_table in TEXT_TABLE_OVERRIDES:
        return TEXT_TABLE_OVERRIDES[check_table]
    tt = check_table + "T"
    cat = field_catalog(conn, tt)
    if not cat:
        return None
    if "SPRAS" not in [r["FIELDNAME"] for r in cat]:   # not a language text table
        return None
    code_keys = _non_client_key(cat)
    text_fields = [r["FIELDNAME"] for r in cat if r["KEYFLAG"] != "X"]
    if not code_keys or not text_fields:
        return None
    return tt, code_keys[-1], text_fields[0]


def values_for_check_table(conn, check_table):
    """[{code, text}] for a check table -- via its text table when one exists.
    Filters only on SPRAS (never MANDT -- RFC_READ_TABLE runs in the logon client).
    """
    found = text_table_of(conn, check_table)
    if found:
        table, code_f, text_f = found
        rows = read_table(conn, table, [code_f, text_f], where=f"SPRAS = '{SPRAS}'")
        return sorted(
            ({"code": r[code_f], "text": r[text_f]} for r in rows if r[code_f]),
            key=lambda x: x["code"],
        )
    # no text table -> codes only (augment by hand if needed)
    keys = _non_client_key(field_catalog(conn, check_table))
    if not keys:
        return []
    code_f = keys[-1]
    seen, out = set(), []
    for r in read_table(conn, check_table, [code_f]):
        c = r[code_f]
        if c and c not in seen:
            seen.add(c)
            out.append({"code": c, "text": ""})
    return sorted(out, key=lambda x: x["code"])

# --------------- domain fixed values (DD04L -> DD07L) + relations ------------
# Many coded fields (procurement type, price control, period indicator...) have
# NO check table -- their allowed values are FIXED VALUES on the data element's
# domain. Read them straight from the DDIC (still clean-core RFC_READ_TABLE).
def domain_of(conn, rollname):
    """Data element (ROLLNAME) -> its domain (DD04L.DOMNAME), or '' if none."""
    if not rollname:
        return ""
    rows = read_table(conn, "DD04L", ["DOMNAME"], where=f"ROLLNAME = '{rollname}'")
    return rows[0]["DOMNAME"] if rows and rows[0].get("DOMNAME") else ""


def domain_fixed_values(conn, domname):
    """[{code, text}] for a domain's FIXED values. Codes live in DD07L; the language
    TEXTS live in the SEPARATE text table DD07T (DD07L's own DDTEXT column is not
    selectable in this release -- reading it returns TABLE_WITHOUT_DATA). So read
    codes from DD07L and texts from DD07T and join on VALPOS -- exactly the
    table/text-table split the check-table path already uses. Empty list if the
    domain has no fixed values (a free CHAR field)."""
    try:
        codes = read_table(conn, "DD07L", ["VALPOS", "DOMVALUE_L"],
                           where=f"DOMNAME = '{domname}' AND AS4LOCAL = 'A'")
    except Exception:
        return []                              # no fixed values (RFC_READ_TABLE: TABLE_WITHOUT_DATA)
    texts = {}
    try:
        for r in read_table(conn, "DD07T", ["VALPOS", "DDTEXT"],
                            where=f"DOMNAME = '{domname}' AND AS4LOCAL = 'A' AND DDLANGUAGE = '{SPRAS}'"):
            texts[r.get("VALPOS", "")] = r.get("DDTEXT", "")
    except Exception:
        pass                                   # texts are a nice-to-have; the codes are the point
    out = []
    for r in sorted(codes, key=lambda x: x.get("VALPOS", "")):
        code = r.get("DOMVALUE_L", "").strip()
        if code:
            out.append({"code": code, "text": texts.get(r.get("VALPOS", ""), "")})
    return out


def scoping_keys(conn, check_table):
    """The check table's key fields OTHER than the code field -- i.e. what the value
    list is SCOPED BY (the 'relation'). e.g. T001L is keyed by (WERKS, LGORT) so a
    storage location is scoped by plant. Empty for a flat single-key list."""
    keys = _non_client_key(field_catalog(conn, check_table))
    return keys[:-1] if len(keys) > 1 else []


# ------------------------------ MAIN ----------------------------------------
def main():
    conn = connect()
    client = os.getenv("SAP_CLIENT", "100")

    # 1) discover coded fields across the base tables. A field is "coded" if it has a
    #    real check table (delivery class not A/L) OR -- failing that -- its domain
    #    carries fixed values. Probe domains only for short CHAR/NUMC fields (the shape
    #    of an indicator) so we don't chase a domain for every text/amount field.
    field_check, field_domain = {}, {}
    dc_cache, dom_by_roll, dom_vals = {}, {}, {}
    for tab in BASE_TABLES:
        for r in field_catalog(conn, tab):
            f = r["FIELDNAME"]
            if f in field_check or f in field_domain:
                continue
            ct = r["CHECKTABLE"]
            if ct and ct != "*" and _VALID_TABLE.match(ct):
                dc = dc_cache.get(ct)
                if dc is None:
                    dc = dc_cache[ct] = delivery_class(conn, ct)
                if dc not in SKIP_DELIVERY_CLASS:      # skip MARA, LFA1, STXFADM, ...
                    field_check[f] = ct
                    continue
            # no usable check table -> try the data element's domain fixed values
            try:
                leng = int(r.get("LENG") or 0)
            except ValueError:
                leng = 0
            if r.get("DATATYPE") not in ("CHAR", "NUMC") or not (0 < leng <= 4):
                continue
            roll = r.get("ROLLNAME")
            if not roll:
                continue
            try:
                dom = dom_by_roll.get(roll)
                if dom is None:
                    dom = dom_by_roll[roll] = domain_of(conn, roll)
                if not dom:
                    continue
                vals = dom_vals.get(dom)
                if vals is None:
                    vals = dom_vals[dom] = domain_fixed_values(conn, dom)
                if vals:
                    field_domain[f] = dom
            except Exception as e:                     # one bad domain shouldn't stop the run
                print(f"  ! domain {f}/{roll}: {e}")

    # 2) read values + scoping keys once per unique check table; drop oversized repositories
    ct_values, ct_scope = {}, {}
    for ct in sorted(set(field_check.values())):
        try:
            vals = values_for_check_table(conn, ct)
            ct_values[ct] = vals if len(vals) <= MAX_VALUES else []
        except Exception as e:                         # one bad table shouldn't stop the run
            ct_values[ct] = []
            print(f"  ! {ct}: {e}")
        try:
            ct_scope[ct] = scoping_keys(conn, ct)
        except Exception:
            ct_scope[ct] = []

    # 3a) full catalog, keyed by DB field -- check-table-backed AND domain-backed,
    #     each with its scoping relation (keyed_by).
    by_db_field = {}
    for f, ct in field_check.items():
        by_db_field[f] = {"check_table": ct, "domain": None,
                          "values": ct_values.get(ct, []), "keyed_by": ct_scope.get(ct, [])}
    for f, dom in field_domain.items():
        by_db_field[f] = {"check_table": None, "domain": dom,
                          "values": dom_vals.get(dom, []), "keyed_by": []}
    by_db_field = dict(sorted(by_db_field.items()))

    # 3b) agent-ready slice, keyed by the OData field name (via the bridge). Only
    #     bridge fields we actually found a value list for -- an empty entry helps no one.
    by_odata_field, unbridged = {}, []
    for odata_field, db_field in FIELD_BRIDGE.items():
        e = by_db_field.get(db_field)
        if e and e["values"]:
            by_odata_field[odata_field] = {"db_field": db_field, **e}
        else:
            unbridged.append(f"{odata_field}->{db_field}")

    out = {
        "_generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "_system": f"{os.getenv('SAP_RFC_HOST') or os.getenv('SAP_HOST')}/{client}",
        "_language": SPRAS,
        "by_odata_field": by_odata_field,   # <- the agent's list_allowed_values reads this
        "by_db_field": by_db_field,         # <- full discovered catalog, for reference
    }
    conn.close()

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Wrote {OUT_PATH}: {len(by_odata_field)} bridged fields, "
          f"{len(by_db_field)} coded DB fields ({len(field_domain)} via domain fixed-values), "
          f"{len(ct_values)} check tables.")
    if unbridged:
        print(f"  bridge entries with no value list (not coded / on an unscanned or master "
              f"table): {', '.join(unbridged)}")


if __name__ == "__main__":
    main()