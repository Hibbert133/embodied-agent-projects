param(
    [string]$Model = "glm-5.2",
    [string]$BaseUrl = "https://api.modelarts-maas.com/anthropic",
    [string]$RunName = "",
    [double]$ApiTimeout = 300,
    [int]$ApiMaxRetries = 2,
    [switch]$PrepareOnly
)
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Python environment not found: $python" }
if (-not $RunName) { $RunName = "utility_" + (Get-Date -Format "yyyyMMdd_HHmmss") }
try {
    $runDir = Join-Path $projectRoot ("outputs\online_utility_agent\" + $RunName)
    $env:ANTHROPIC_BASE_URL = $BaseUrl
    $arguments = @((Join-Path $projectRoot "scripts\run_online_utility_agent.py"), "--model", $Model, "--base-url", $BaseUrl, "--api-timeout", $ApiTimeout, "--api-max-retries", $ApiMaxRetries, "--output-dir", $runDir)
    if ($PrepareOnly) {
        $arguments += "--prepare-only"
    } else {
        $secureKey = Read-Host "Enter a new ANTHROPIC_API_KEY (input is hidden)" -AsSecureString
        $env:ANTHROPIC_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
    }
    & $python @arguments
    exit $LASTEXITCODE
} finally {
    Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:ANTHROPIC_BASE_URL -ErrorAction SilentlyContinue
    Remove-Variable secureKey -ErrorAction SilentlyContinue
}
