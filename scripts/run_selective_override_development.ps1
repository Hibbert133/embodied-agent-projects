param([string]$BaseUrl = "")

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "common\agent_api.ps1")
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$apiState = Enter-AgentApiEnvironment -ProjectRoot $projectRoot -RequestedModel "glm-5.2" -RequestedBaseUrl $BaseUrl
try {
    & $python (Join-Path $projectRoot "scripts\generate_selective_override_manifest.py")
    if ($LASTEXITCODE -ne 0) { throw "Selective-override manifest generation failed" }
    $manifest = Get-ChildItem (Join-Path $projectRoot "outputs\probemem_online\selective_override_runs") -Filter immutable_manifest.json -Recurse |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    & $python (Join-Path $projectRoot "scripts\run_selective_override_development.py") `
        --manifest $manifest.FullName --base-url $apiState.BaseUrl
    if ($LASTEXITCODE -notin @(0, 2)) { throw "Selective-override development failed with exit code $LASTEXITCODE" }
    & $python (Join-Path $projectRoot "scripts\analyze_selective_override_development.py") `
        --run-dir $manifest.Directory.FullName
}
finally {
    Exit-AgentApiEnvironment -State $apiState
}
