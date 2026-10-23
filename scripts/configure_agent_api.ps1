param(
    [string]$BaseUrl = "https://api.modelarts-maas.com/anthropic",
    [string]$Model = "glm-5.2",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$configPath = Join-Path $projectRoot "config\agent_api.local.clixml"
if ((Test-Path -LiteralPath $configPath) -and -not $Force) {
    throw "Local API configuration already exists. Use -Force to replace it."
}
if (-not $BaseUrl.Trim() -or -not $Model.Trim()) {
    throw "BaseUrl and Model must be non-empty."
}

$secureKey = Read-Host "Enter a newly issued API key (input is hidden)" -AsSecureString
$config = [pscustomobject]@{
    SchemaVersion = 1
    Provider = "anthropic-compatible"
    BaseUrl = $BaseUrl
    Model = $Model
    ApiKey = $secureKey
    CreatedAtUtc = [DateTime]::UtcNow.ToString("o")
}
$directory = Split-Path -Parent $configPath
New-Item -ItemType Directory -Path $directory -Force | Out-Null
$temporary = Join-Path $directory "agent_api.secret.tmp"
try {
    $config | Export-Clixml -LiteralPath $temporary -Depth 4
    Move-Item -LiteralPath $temporary -Destination $configPath -Force
}
finally {
    Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    Remove-Variable secureKey -ErrorAction SilentlyContinue
}
Write-Output "Configured local Agent API provider=anthropic-compatible model=$Model"
Write-Output "Encrypted credential: $configPath"
