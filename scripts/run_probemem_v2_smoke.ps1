param(
    [string]$Manifest = "",
    [double]$ApiTimeout = 300
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "common\agent_api.ps1")

if (-not $Manifest) {
    throw "Pass -Manifest outputs\probemem_v2\runs\<run-id>\manifest.json"
}

$state = $null
try {
    $state = Enter-AgentApiEnvironment -ProjectRoot $root -RequestedModel "glm-5.2"
    & (Join-Path $root ".venv\Scripts\python.exe") `
        (Join-Path $PSScriptRoot "run_probemem_v2_smoke.py") `
        --manifest $Manifest `
        --api-timeout $ApiTimeout
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Exit-AgentApiEnvironment -State $state
}
