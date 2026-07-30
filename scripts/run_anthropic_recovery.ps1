param(
    [string]$Model = "",
    [string]$BaseUrl = "",
    [int]$Seed = 148,
    [int]$MaxTrials = 5,
    [double]$ApiTimeout = 180,
    [int]$ApiMaxRetries = 2,
    [string]$RunName = "",
    [int]$Fps = 30,
    [string]$BiasAxis = "x",
    [string]$BiasSign = "positive",
    [double]$BiasMagnitude = 0.145
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
    if (-not $RunName) {
        $RunName = "glm51_seed${Seed}_video"
    }
    $runDir = Join-Path $projectRoot ("outputs\recovery\runs\" + $RunName)
    & $python (Join-Path $projectRoot "scripts\run_recovery_agent.py") `
        --planner anthropic `
        --model $Model `
        --base-url $BaseUrl `
        --seed-start $Seed `
        --num-episodes 1 `
        --max-trials $MaxTrials `
        --api-timeout $ApiTimeout `
        --api-max-retries $ApiMaxRetries `
        --output-csv (Join-Path $runDir "trials.csv") `
        --audit-jsonl (Join-Path $runDir "planner_audit.jsonl") `
        --trajectory-dir (Join-Path $runDir "trajectories") `
        --video-dir (Join-Path $runDir "videos") `
        --fps $Fps `
        --bias-axis $BiasAxis `
        --bias-sign $BiasSign `
        --bias-magnitude $BiasMagnitude
    exit $LASTEXITCODE
}
finally {
    Exit-AgentApiEnvironment -State $apiState
}
