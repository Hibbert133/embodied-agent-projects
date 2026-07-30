param(
    [string]$BaseUrl = "",
    [string]$Model = "",
    [int]$ApiTimeout = 300,
    [string]$RunName = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "common\agent_api.ps1")
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Missing .venv Python: $python" }
$apiState = Enter-AgentApiEnvironment -ProjectRoot $root -RequestedModel $Model -RequestedBaseUrl $BaseUrl
$Model = $apiState.Model
$BaseUrl = $apiState.BaseUrl
if (-not $RunName) { $RunName = Get-Date -Format "yyyyMMdd_HHmmss" }
$outputDir = Join-Path $root "outputs\autoresearch\search_runs\$RunName"
try {
    & $python (Join-Path $root "scripts\run_budgeted_autoresearch.py") --model $Model --base-url $BaseUrl --api-timeout $ApiTimeout --output-dir $outputDir
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally { Exit-AgentApiEnvironment -State $apiState }
