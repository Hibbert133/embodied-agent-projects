param(
    [string]$Model = "glm-5.1",
    [string]$BaseUrl = "https://api.modelarts-maas.com/anthropic",
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
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found: $python"
}

$secureKey = Read-Host "Enter a new ANTHROPIC_API_KEY (input is hidden)" -AsSecureString
try {
    if (-not $RunName) {
        $RunName = "glm51_seed${Seed}_video"
    }
    $runDir = Join-Path $projectRoot ("outputs\recovery\runs\" + $RunName)
    $env:ANTHROPIC_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
    $env:ANTHROPIC_BASE_URL = $BaseUrl
    $env:LLM_MODEL = $Model
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
    Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:ANTHROPIC_BASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:LLM_MODEL -ErrorAction SilentlyContinue
    Remove-Variable secureKey -ErrorAction SilentlyContinue
}
