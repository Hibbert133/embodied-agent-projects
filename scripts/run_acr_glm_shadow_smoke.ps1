param([double]$ApiTimeout = 300)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "common\agent_api.ps1")
$state = $null
try {
    $state = Enter-AgentApiEnvironment -ProjectRoot $root -RequestedModel "glm-5.2"
    & (Join-Path $root ".venv\Scripts\python.exe") `
        (Join-Path $PSScriptRoot "run_acr_glm_shadow_smoke.py") `
        --api-timeout $ApiTimeout
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Exit-AgentApiEnvironment -State $state
}
