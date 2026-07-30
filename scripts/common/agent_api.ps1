function Enter-AgentApiEnvironment {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [string]$RequestedModel = "",
        [string]$RequestedBaseUrl = ""
    )

    $names = @("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "LLM_MODEL")
    $original = @{}
    foreach ($name in $names) {
        $original[$name] = @{
            Exists = Test-Path -LiteralPath ("Env:" + $name)
            Value = [Environment]::GetEnvironmentVariable($name, "Process")
        }
    }

    $configPath = Join-Path $ProjectRoot "config\agent_api.local.clixml"
    $config = $null
    if (Test-Path -LiteralPath $configPath) {
        $config = Import-Clixml -LiteralPath $configPath
        if ($config.SchemaVersion -ne 1 -or $config.Provider -ne "anthropic-compatible") {
            throw "Unsupported local Agent API configuration: $configPath"
        }
        if ($config.ApiKey -isnot [Security.SecureString]) {
            throw "Local Agent API configuration does not contain a DPAPI SecureString"
        }
    }

    $key = $env:ANTHROPIC_API_KEY
    if (-not $key -and $null -ne $config) {
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($config.ApiKey)
        try {
            $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
        }
        finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        }
    }
    if (-not $key) {
        throw "No local API credential is configured. Run .\scripts\configure_agent_api.ps1 once."
    }

    $baseUrl = $RequestedBaseUrl
    if (-not $baseUrl) { $baseUrl = $env:ANTHROPIC_BASE_URL }
    if (-not $baseUrl -and $null -ne $config) { $baseUrl = [string]$config.BaseUrl }
    if (-not $baseUrl) { $baseUrl = "https://api.modelarts-maas.com/anthropic" }

    $model = $RequestedModel
    if (-not $model) { $model = $env:LLM_MODEL }
    if (-not $model -and $null -ne $config) { $model = [string]$config.Model }
    if (-not $model) { $model = "glm-5.2" }

    $env:ANTHROPIC_API_KEY = $key
    $env:ANTHROPIC_BASE_URL = $baseUrl
    $env:LLM_MODEL = $model
    return @{
        Original = $original
        Model = $model
        BaseUrl = $baseUrl
        ConfigPath = $configPath
    }
}

function Exit-AgentApiEnvironment {
    param([hashtable]$State)
    if ($null -eq $State) { return }
    foreach ($name in $State.Original.Keys) {
        $entry = $State.Original[$name]
        if ($entry.Exists) {
            [Environment]::SetEnvironmentVariable($name, $entry.Value, "Process")
        }
        else {
            Remove-Item -LiteralPath ("Env:" + $name) -ErrorAction SilentlyContinue
        }
    }
}
