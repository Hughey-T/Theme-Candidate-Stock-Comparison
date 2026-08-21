[CmdletBinding()]
param(
    [string]$ContainerName = 'theme-compare',
    [string]$Since = '10m'
)

$ErrorActionPreference = 'Stop'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'docker command was not found.'
}

$running = (& docker inspect -f '{{.State.Running}}' $ContainerName 2>$null | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $running -ne 'true') {
    throw "Container is not running: $ContainerName"
}

$raw = & docker logs $ContainerName --since $Since --timestamps 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Could not read logs from container: $ContainerName"
}

$entries = @()
foreach ($line in $raw) {
    $text = [string]$line
    $match = [regex]::Match(
        $text,
        '^(?<timestamp>\S+)\s+.*POST /v2/sessions HTTP/[0-9.]+"\s+(?<status>\d{3})'
    )
    if ($match.Success) {
        $entries += [pscustomobject]@{
            Timestamp = $match.Groups['timestamp'].Value
            Status = [int]$match.Groups['status'].Value
        }
    }
}

if ($entries.Count -eq 0) {
    Write-Host 'LIVE ACTION DIAGNOSTIC: no recent POST /v2/sessions reached the runtime.'
    Write-Host "Window: $Since"
    Write-Host 'If the Custom GPT just reported an API error, the failure happened before the request reached this runtime.'
    Write-Host 'No request body, Authorization header, or API key was inspected.'
    exit 2
}

$recent = @($entries | Select-Object -Last 10)
Write-Host 'Recent POST /v2/sessions entries:'
foreach ($entry in $recent) {
    Write-Host ('  ' + $entry.Timestamp + '  HTTP ' + $entry.Status)
}
$latest = $recent[-1]
Write-Host ('Latest status: ' + $latest.Status)

switch ($latest.Status) {
    201 {
        Write-Host 'DIAGNOSIS: a recent session-create request reached the runtime and succeeded.'
        exit 0
    }
    401 {
        Write-Host 'DIAGNOSIS: authentication failure. The Custom GPT Action Bearer API key configuration is the next fix target.'
        exit 10
    }
    422 {
        Write-Host 'DIAGNOSIS: authentication succeeded, but the create-session request failed runtime validation.'
        Write-Host 'Next target: request-body compatibility / validation diagnostics.'
        exit 20
    }
    default {
        Write-Host ('DIAGNOSIS: runtime returned HTTP ' + $latest.Status + '. Inspect this status before changing the Action schema.')
        exit 30
    }
}
