"""run_demand.py -- launch the PIR (Planned Independent Requirement) server on :8003 in the rig's OWN venv.

Uses mcp-plndindepreqmt (jl-recon/d2m-cf/mcp-plndindepreqmt) -- the canonically-named server wrapping
API_PLND_INDEP_RQMT_SRV (type VSF / version 00), the make-to-stock forecast demand MRP actually consumes.
It supersedes the older mcp-demand app (same schema, clearer tool names: create/read/change_plndindepreqmt).
Unlike the RFC servers on :8001/:8002 it is PURE OData (requests) -- no NWRFC SDK -- so it runs right
alongside web.py. It only needs the rig's SAP credentials pointed at the REAL appliance.

    python run_demand.py        # serves http://127.0.0.1:8003/mcp  (streamable-http)

planning_client.create_demand() bridges to it via DEMAND_MCP_URL (default that same URL).
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_HERE = Path(__file__).resolve().parent
load_dotenv(_HERE / ".env")                       # rig creds: SAP_USER / SAP_PASS / SAP_CLIENT / port

# The rig's SAP_HOST is the DUMMY OData hostname (vhcals4hci.dummy.nodomain); mcp-demand talks straight
# to the appliance over the PUBLIC IP, which the rig stores as SAP_RFC_HOST. Point sap_client there and
# do NOT let the dummy SAP_HOST leak through.
os.environ["SAP_HOST"] = (os.getenv("SAP_RFC_HOST") or "54.156.89.129").strip().strip("'\"")
os.environ.setdefault("SAP_HTTPS_PORT", os.getenv("SAP_HTTPS_PORT", "44301"))
os.environ.setdefault("SAP_CLIENT", os.getenv("SAP_CLIENT", "100"))
os.environ["PORT"] = os.getenv("DEMAND_PORT", "8003")

_DEMAND_DIR = _HERE.parent / "jl-recon" / "d2m-cf" / "mcp-plndindepreqmt"
if not (_DEMAND_DIR / "create_plndindepreqmt.py").exists():
    sys.exit(f"mcp-plndindepreqmt not found at {_DEMAND_DIR}")
sys.path.insert(0, str(_DEMAND_DIR))

import create_plndindepreqmt as app  # noqa: E402  -- builds FastMCP bound to PORT at import time

print(f"mcp-plndindepreqmt (PIR / VSF demand) -> http://127.0.0.1:{os.environ['PORT']}/mcp"
      f"  [SAP {os.environ['SAP_HOST']}:{os.environ['SAP_HTTPS_PORT']} "
      f"client {os.environ['SAP_CLIENT']} user {os.getenv('SAP_USER')}]", flush=True)
app.mcp.run(transport="streamable-http")
