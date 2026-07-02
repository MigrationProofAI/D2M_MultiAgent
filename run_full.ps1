# Launch the D2M rig in FULL multi-agent mode on port 9000.
# Run from this folder in CONDA BASE (has pyrfc).   .\run_full.ps1
#
# Starts the verify+heal multi-agent loop with extended-thinking reasoning, fresh-build genesis
# (no dedup / no reuse of old materials), and Claude on AI Core (no out-of-pocket spend).
#
# NOTE: the two RFC servers are separate processes (start them once, in MCPCTypeNWRFC):
#     python sap_prodvers_mcp.py      # :8002  routing + production version
#     python sap_planning_mcp.py      # :8001  MRP (BAPI_MATERIAL_PLANNING)
# The PIR demand server (:8003) is PURE OData -- no NWRFC SDK -- so this script starts it for you below.

$env:MODEL_PROVIDER  = "anthropic"   # Claude (Sonnet) on SAP AI Core
$env:GENESIS_DEDUP   = "off"         # ALWAYS create fresh -- never reuse day-old materials
$env:RIG_ORCHESTRATE = "on"          # the Doer -> Verifier -> heal multi-agent loop
$env:RIG_HEAL_MAX    = "5"           # max auto-heal passes
$env:RIG_THINKING    = "on"          # extended thinking (the live reasoning chain)
$env:RIG_BOARD       = "on"          # convene the cross-functional board on each genesis preview
$env:RIG_TTS         = "on"          # nova voice for the Tour / Guide / Intro (cached, ~free)
$env:PYTHONIOENCODING = "utf-8"

Write-Host "D2M FULL multi-agent  ->  http://localhost:9000" -ForegroundColor Cyan
Write-Host ("  ORCHESTRATE={0}  HEAL_MAX={1}  THINKING={2}  DEDUP={3}  PROVIDER={4}" -f `
    $env:RIG_ORCHESTRATE, $env:RIG_HEAL_MAX, $env:RIG_THINKING, $env:GENESIS_DEDUP, $env:MODEL_PROVIDER) -ForegroundColor DarkGray
Write-Host "  (RFC servers :8002 / :8001 are separate -- start them in MCPCTypeNWRFC)" -ForegroundColor DarkGray

# PIR demand server (:8003) -- runs in THIS venv (pure OData). Start it unless it's already up.
$demandUp = $false
try { $demandUp = (Test-NetConnection -ComputerName 127.0.0.1 -Port 8003 -WarningAction SilentlyContinue -InformationLevel Quiet) } catch {}
if ($demandUp) {
    Write-Host "  demand server :8003 already running -- reusing it" -ForegroundColor DarkGray
} else {
    Write-Host "  starting PIR demand server :8003 (mcp-plndindepreqmt, VSF/00)" -ForegroundColor DarkGray
    Start-Process -FilePath "python" -ArgumentList "run_demand.py" -WorkingDirectory $PSScriptRoot -WindowStyle Minimized
}

# MD04 read server (:8004) -- mcp-mrp, pure OData. Verification view for MRP execution.
$mrpviewUp = $false
try { $mrpviewUp = (Test-NetConnection -ComputerName 127.0.0.1 -Port 8004 -WarningAction SilentlyContinue -InformationLevel Quiet) } catch {}
if ($mrpviewUp) {
    Write-Host "  MD04 read server :8004 already running -- reusing it" -ForegroundColor DarkGray
} else {
    Write-Host "  starting MD04 read server :8004 (mcp-mrp, read_mrp_list)" -ForegroundColor DarkGray
    Start-Process -FilePath "python" -ArgumentList "run_mrpview.py" -WorkingDirectory $PSScriptRoot -WindowStyle Minimized
}

python -m uvicorn web:app --host 0.0.0.0 --port 9000
