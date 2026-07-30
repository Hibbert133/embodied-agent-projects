param(
    [string]$Model = "",
    [string]$BaseUrl = "",
    [string]$RunName = "",
    [double]$ApiTimeout = 300,
    [int]$ApiMaxRetries = 2,
    [switch]$PrepareOnly
)
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "common\agent_api.ps1")
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Python environment not found: $python" }
if (-not $RunName) { $RunName = "utility_" + (Get-Date -Format "yyyyMMdd_HHmmss") }
$apiState = $null
try {
    if ($PrepareOnly) {
        if (-not $Model) { $Model = "glm-5.1" }
        if (-not $BaseUrl) { $BaseUrl = "https://api.modelarts-maas.com/anthropic" }
    } else {
        $apiState = Enter-AgentApiEnvironment -ProjectRoot $projectRoot -RequestedModel $Model -RequestedBaseUrl $BaseUrl
        $Model = $apiState.Model
        $BaseUrl = $apiState.BaseUrl
    }
    $runDir = Join-Path $projectRoot ("outputs\online_utility_agent\" + $RunName)
    $arguments = @((Join-Path $projectRoot "scripts\run_online_utility_agent.py"), "--model", $Model, "--base-url", $BaseUrl, "--api-timeout", $ApiTimeout, "--api-max-retries", $ApiMaxRetries, "--output-dir", $runDir)
    if ($PrepareOnly) {
        $arguments += "--prepare-only"
    }
    & $python @arguments
    exit $LASTEXITCODE
} finally {
    Exit-AgentApiEnvironment -State $apiState
}
