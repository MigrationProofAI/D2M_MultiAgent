# Launch the D2M Test Rig with the standard TESTING config.
# Run from this folder in CONDA BASE (has pyrfc):   .\run_rig.ps1
#
#   MODEL_PROVIDER = anthropic  -> Claude Sonnet 4.6 via SAP GenAI Hub
#                                  (use "genaihub" for gpt-4o, "openai" for direct OpenAI)
#   GENESIS_DEDUP  = off        -> every genesis run CREATES fresh, no semantic reuse
#                                  (omit / set "on" to re-enable dedup)

$env:MODEL_PROVIDER = "anthropic"
$env:GENESIS_DEDUP  = "off"

Write-Host "Starting D2M rig -> MODEL_PROVIDER=$($env:MODEL_PROVIDER)  GENESIS_DEDUP=$($env:GENESIS_DEDUP)" -ForegroundColor Cyan
python web.py
