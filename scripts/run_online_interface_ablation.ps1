param(
    [string]$BaseUrl = "https://api.modelarts-maas.com/anthropic",
    [double]$ApiTimeout = 300,
    [int]$ApiMaxRetries = 2
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found: $python"
}
$secureKey = Read-Host "Enter a new ANTHROPIC_API_KEY (input is hidden)" -AsSecureString
try {
    $env:ANTHROPIC_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
    $env:ANTHROPIC_BASE_URL = $BaseUrl

    $skillsOutput = Join-Path $projectRoot "outputs\online_planar_agent\glm51_skills_dev"
    & $python (Join-Path $projectRoot "scripts\run_skill_grounded_planar_agent.py") `
        --seeds 250 251 252 253 254 `
        --bias-x 0.14 --bias-y -0.14 --max-steps 500 `
        --model glm-5.1 --base-url $BaseUrl `
        --api-timeout $ApiTimeout --api-max-retries $ApiMaxRetries `
        --output-dir $skillsOutput
    if ($LASTEXITCODE -ne 0) {
        throw "GLM-5.1 skill-grounded run failed with exit code $LASTEXITCODE"
    }

    $rawOutput = Join-Path $projectRoot "outputs\online_planar_agent\glm52_raw_dev"
    & $python (Join-Path $projectRoot "scripts\run_online_planar_agent.py") `
        --seeds 250 251 252 253 254 `
        --bias-x 0.14 --bias-y -0.14 --max-steps 500 `
        --model glm-5.2 --base-url $BaseUrl `
        --api-timeout $ApiTimeout --api-max-retries $ApiMaxRetries `
        --output-dir $rawOutput
    if ($LASTEXITCODE -ne 0) {
        throw "GLM-5.2 raw-probe run failed with exit code $LASTEXITCODE"
    }
}
finally {
    Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:ANTHROPIC_BASE_URL -ErrorAction SilentlyContinue
    Remove-Variable secureKey -ErrorAction SilentlyContinue
}
