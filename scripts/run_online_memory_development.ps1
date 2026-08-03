param(
    [string]$BaseUrl = ""
)

$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "common\agent_api.ps1")
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$apiState = Enter-AgentApiEnvironment -ProjectRoot $projectRoot -RequestedModel "glm-5.2" -RequestedBaseUrl $BaseUrl
try {
    & $python (Join-Path $projectRoot "scripts\generate_online_memory_manifest.py")
    if ($LASTEXITCODE -ne 0) { throw "Gate C manifest generation failed" }
    $manifest = Get-ChildItem (Join-Path $projectRoot "outputs\probemem_online\sequential_runs") -Filter immutable_manifest.json -Recurse |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    & $python (Join-Path $projectRoot "scripts\run_online_memory_development.py") --manifest $manifest.FullName --base-url $apiState.BaseUrl
    if ($LASTEXITCODE -ne 0) { throw "Gate C development failed with exit code $LASTEXITCODE" }
}
finally {
    Exit-AgentApiEnvironment -State $apiState
}
