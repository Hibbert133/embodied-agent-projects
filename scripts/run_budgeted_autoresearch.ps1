param(
    [string]$BaseUrl = "https://api.modelarts-maas.com/anthropic",
    [string]$Model = "glm-5.2",
    [int]$ApiTimeout = 300,
    [string]$RunName = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Missing .venv Python: $python" }
if (-not $env:ANTHROPIC_API_KEY) {
    $secure = Read-Host "Enter a new ANTHROPIC_API_KEY (input is hidden)" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $env:ANTHROPIC_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}
$env:ANTHROPIC_BASE_URL = $BaseUrl
if (-not $RunName) { $RunName = Get-Date -Format "yyyyMMdd_HHmmss" }
$outputDir = Join-Path $root "outputs\autoresearch\search_runs\$RunName"
try {
    & $python (Join-Path $root "scripts\run_budgeted_autoresearch.py") --model $Model --base-url $BaseUrl --api-timeout $ApiTimeout --output-dir $outputDir
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally { Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue }
