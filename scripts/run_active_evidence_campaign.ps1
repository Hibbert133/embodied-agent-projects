param(
    [string]$Config = "configs\campaigns\active_evidence_glm52_pilot.json",
    [string]$OutputDir = "",
    [string]$Model = "",
    [string]$BaseUrl = "",
    [double]$ApiTimeout = 300,
    [int]$ApiMaxRetries = 2
)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "common\agent_api.ps1")
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Python environment not found: $python" }
$apiState = Enter-AgentApiEnvironment -ProjectRoot $projectRoot -RequestedModel $Model -RequestedBaseUrl $BaseUrl
try {
    $configPath = if ([IO.Path]::IsPathRooted($Config)) { $Config } else { Join-Path $projectRoot $Config }
    $arguments = @(
        (Join-Path $projectRoot "scripts\run_active_evidence_campaign.py"),
        "--config", $configPath,
        "--model", $apiState.Model,
        "--base-url", $apiState.BaseUrl,
        "--api-timeout", $ApiTimeout,
        "--api-max-retries", $ApiMaxRetries
    )
    if ($OutputDir) { $arguments += @("--output-dir", $OutputDir) }
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Exit-AgentApiEnvironment -State $apiState
}
