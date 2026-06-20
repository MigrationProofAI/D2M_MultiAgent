"""Assert a value is in the LIVE SAP codebook for a field. RUN, don't read -- this costs ~0 context
(only the one-line verdict enters the conversation, never this source).

    check_value.py <field> <value>     # exit 0 = VALID, 1 = NOT FOUND
"""
import os
import sys

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(_root, "mcp_server"))
from dotenv import load_dotenv
load_dotenv(os.path.join(_root, ".env"))
from sap import list_allowed_values

if len(sys.argv) < 3:
    print("usage: check_value.py <field> <value>")
    sys.exit(2)

field, value = sys.argv[1], sys.argv[2]
codebook = list_allowed_values(field) or ""
ok = value.lower() in codebook.lower()
print(f"{value!r} in {field} codebook: {'VALID' if ok else 'NOT FOUND'}")
sys.exit(0 if ok else 1)
