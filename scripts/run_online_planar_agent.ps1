param(
    [string]$Model = "glm-5.1",
    [string]$BaseUrl = "https://api.modelarts-maas.com/anthropic",
    [string]$RunName = "glm51_planar_dev",
    [double]$ApiTimeout = 180,
    [int]$ApiMaxRetries = 2
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found: $python"
}

$secureKey = Read-Host "Enter a new ANTHROPIC_API_KEY (input is hidden)" -AsSecureString
try {
    $runDir = Join-Path $projectRoot ("outputs\online_planar_agent\" + $RunName)
    $env:ANTHROPIC_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
    $env:ANTHROPIC_BASE_URL = $BaseUrl
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
    Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:ANTHROPIC_BASE_URL -ErrorAction SilentlyContinue
    Remove-Variable secureKey -ErrorAction SilentlyContinue
}
