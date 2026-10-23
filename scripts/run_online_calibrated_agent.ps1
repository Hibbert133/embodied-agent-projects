param([Parameter(Mandatory = $true)][string]$Manifest)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "common\agent_api.ps1")
$state = $null
try {
    $state = Enter-AgentApiEnvironment -ProjectRoot $root -RequestedModel "glm-5.2"
    $arguments = @((Join-Path $PSScriptRoot "run_online_calibrated_agent.py"), "--manifest", $Manifest)
    & (Join-Path $root ".venv\Scripts\python.exe") @arguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Exit-AgentApiEnvironment -State $state
}
