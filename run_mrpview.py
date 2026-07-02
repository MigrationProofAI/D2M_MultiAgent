"""run_mrpview.py -- launch the MD04 read server (mcp-mrp) on :8004 in the rig's OWN venv.

mcp-mrp (jl-recon/d2m-cf/mcp-mrp) wraps API_MRP_MATERIALS_SRV_01 (READ): the MD04 stock/requirements
list -- what an MRP run PRODUCED (stock, planned orders, purchase requisitions, planned independent
requirements, dependent requirements). It is the verification view for an MRP execution. Like the PIR
server it is PURE OData (requests) -- no NWRFC SDK -- so it runs right alongside web.py; it only needs
the rig's SAP credentials pointed at the REAL appliance.

    python run_mrpview.py        # serves http://127.0.0.1:8004/mcp  (streamable-http)

planning_client.read_mrp_list()/read_mrp_material() bridge to it via MRPVIEW_MCP_URL (that same URL).
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_HERE = Path(__file__).resolve().parent
load_dotenv(_HERE / ".env")                       # rig creds: SAP_USER / SAP_PASS / SAP_CLIENT / port

# The rig's SAP_HOST is the DUMMY OData hostname (vhcals4hci.dummy.nodomain); mcp-mrp talks straight to
# the appliance over the PUBLIC IP, which the rig stores as SAP_RFC_HOST. Point sap_client there and do
# NOT let the dummy SAP_HOST leak through.
os.environ["SAP_HOST"] = (os.getenv("SAP_RFC_HOST") or "54.156.89.129").strip().strip("'\"")
os.environ.setdefault("SAP_HTTPS_PORT", os.getenv("SAP_HTTPS_PORT", "44301"))
os.environ.setdefault("SAP_CLIENT", os.getenv("SAP_CLIENT", "100"))
os.environ["PORT"] = os.getenv("MRPVIEW_PORT", "8004")

_MRP_DIR = _HERE.parent / "jl-recon" / "d2m-cf" / "mcp-mrp"
if not (_MRP_DIR / "app.py").exists():
    sys.exit(f"mcp-mrp not found at {_MRP_DIR}")
sys.path.insert(0, str(_MRP_DIR))

import app  # noqa: E402  -- builds FastMCP('mcp-mrp') bound to PORT at import time

print(f"mcp-mrp (MD04 stock/requirements READ) -> http://127.0.0.1:{os.environ['PORT']}/mcp"
      f"  [SAP {os.environ['SAP_HOST']}:{os.environ['SAP_HTTPS_PORT']} "
      f"client {os.environ['SAP_CLIENT']} user {os.getenv('SAP_USER')}]", flush=True)
app.mcp.run(transport="streamable-http")
