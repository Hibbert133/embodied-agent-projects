param(
    [string]$Model = "",
    [string]$BaseUrl = "",
    [string]$RunName = "glm52_planar_dev",
    [double]$ApiTimeout = 180,
    [int]$ApiMaxRetries = 2
)

$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "common\agent_api.ps1")
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found: $python"
}

$apiState = Enter-AgentApiEnvironment -ProjectRoot $projectRoot -RequestedModel $Model -RequestedBaseUrl $BaseUrl
$Model = $apiState.Model
$BaseUrl = $apiState.BaseUrl
try {
    $runDir = Join-Path $projectRoot ("outputs\online_planar_agent\" + $RunName)
    & $python (Join-Path $projectRoot "scripts\run_online_planar_agent.py") `
        --seeds 250 251 252 253 254 `
        --bias-x 0.14 `
        --bias-y -0.14 `
        --max-steps 500 `
        --model $Model `
        --base-url $BaseUrl `
        --api-timeout $ApiTimeout `
        --api-max-retries $ApiMaxRetries `
        --output-dir $runDir
    exit $LASTEXITCODE
}
finally {
    Exit-AgentApiEnvironment -State $apiState
}
