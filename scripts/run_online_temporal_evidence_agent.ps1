param(
    [string]$BaseUrl = "",
    [string]$Model = "glm-5.2",
    [double]$ApiTimeout = 300,
    [int]$ApiMaxRetries = 2,
    [int]$MaxApiCalls = 10,
    [string]$OutputDir = "outputs\online_evidence_agent\glm52_temporal_development_v1"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "common\agent_api.ps1")
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found: $python"
}
$apiState = Enter-AgentApiEnvironment `
    -ProjectRoot $projectRoot `
    -RequestedModel $Model `
    -RequestedBaseUrl $BaseUrl
try {
    & $python (Join-Path $projectRoot "scripts\run_online_temporal_evidence_agent.py") `
        --model $apiState.Model `
        --base-url $apiState.BaseUrl `
        --api-timeout $ApiTimeout `
        --api-max-retries $ApiMaxRetries `
        --max-api-calls $MaxApiCalls `
        --output-dir (Join-Path $projectRoot $OutputDir)
    if ($LASTEXITCODE -ne 0) {
        throw "Online temporal evidence agent failed with exit code $LASTEXITCODE"
    }
}
finally {
    Exit-AgentApiEnvironment -State $apiState
}
