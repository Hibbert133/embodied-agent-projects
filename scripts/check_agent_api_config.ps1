$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$configPath = Join-Path $projectRoot "config\agent_api.local.clixml"
if (-not (Test-Path -LiteralPath $configPath)) {
    Write-Output "configured=False"
    exit 1
}
$config = Import-Clixml -LiteralPath $configPath
if ($config.SchemaVersion -ne 1 -or $config.ApiKey -isnot [Security.SecureString]) {
    throw "Invalid local Agent API configuration."
}
Write-Output "configured=True"
Write-Output ("provider=" + $config.Provider)
Write-Output ("base_url=" + $config.BaseUrl)
Write-Output ("model=" + $config.Model)
