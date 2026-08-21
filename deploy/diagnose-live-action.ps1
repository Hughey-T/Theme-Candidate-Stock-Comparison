[CmdletBinding()]
param(
    [string]$ContainerName = 'theme-compare',
    [string]$Since = '30m'
)

$ErrorActionPreference = 'Stop'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'docker command was not found.'
}

$running = (& docker inspect -f '{{.State.Running}}' $ContainerName 2>$null | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $running -ne 'true') {
    throw "Container is not running: $ContainerName"
}

$raw = & docker logs $ContainerName --since $Since 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Could not read logs from container: $ContainerName"
}

$statuses = @()
foreach ($line in $raw) {
    $text = [string]$line
    $match = [regex]::Match($text, 'POST /v2/sessions HTTP/[0-9.]+"\s+(?<status>\d{3})')
    if ($match.Success) {
        $statuses += [int]$match.Groups['status'].Value
    }
}

if ($statuses.Count -eq 0) {
    Write-Host 'LIVE ACTION DIAGNOSTIC: no POST /v2/sessions access-log entries found.'
    Write-Host "Window: $Since"
    Write-Host 'No request body, Authorization header, or API key was inspected.'
    exit 2
}

$recent = @($statuses | Select-Object -Last 10)
Write-Host ('Recent POST /v2/sessions HTTP statuses: ' + ($recent -join ', '))
Write-Host ('Latest status: ' + $recent[-1])

switch ($recent[-1]) {
    201 {
        Write-Host 'DIAGNOSIS: session creation reached the runtime and succeeded.'
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
        Write-Host ('DIAGNOSIS: runtime returned HTTP ' + $recent[-1] + '. Inspect this status before changing the Action schema.')
        exit 30
    }
}
