[CmdletBinding()]
param(
    [string]$ContainerName = 'theme-compare'
)

$ErrorActionPreference = 'Stop'

$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCommand) { throw 'docker command was not found.' }

$running = (& docker inspect -f '{{.State.Running}}' $ContainerName 2>$null | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $running -ne 'true') {
    throw "Container is not running: $ContainerName"
}

$pythonCode = @'
import json
from pathlib import Path

root = Path('/data/sessions')
paths = list(root.glob('s_*.v2.json'))
if not paths:
    raise SystemExit('no persisted v2 session found')
path = max(paths, key=lambda item: item.stat().st_mtime_ns)
state = json.loads(path.read_text(encoding='utf-8'))
artifacts = state.get('artifacts', [])
result = {
    'session_id': state.get('session_id'),
    'workflow': state.get('workflow'),
    'generation_id': state.get('generation_id'),
    'status': state.get('status'),
    'current_phase': state.get('phase'),
    'artifact_count': len(artifacts),
    'completed_phases': [item.get('phase') for item in artifacts if isinstance(item, dict)],
}
print(json.dumps(result, separators=(',', ':')))
'@

$raw = (& docker exec $ContainerName python -c $pythonCode 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Could not inspect persisted v2 progress: $raw"
}

try {
    $state = $raw | ConvertFrom-Json
}
catch {
    throw 'Persisted v2 progress diagnostic returned invalid JSON.'
}

Write-Host '=== Latest persisted v2 session progress ==='
Write-Host ('Session: ' + $state.session_id)
Write-Host ('Workflow: ' + $state.workflow)
Write-Host ('Generation: ' + $state.generation_id)
Write-Host ('Status: ' + $state.status)
Write-Host ('Current phase: ' + $state.current_phase)
Write-Host ('Artifact count: ' + $state.artifact_count)
$completed = @($state.completed_phases)
if ($completed.Count -gt 0) {
    Write-Host ('Completed phases: ' + ($completed -join ','))
}
else {
    Write-Host 'Completed phases: <none>'
}
Write-Host 'No artifact payload, evidence text, API key, or Authorization header was printed.'
