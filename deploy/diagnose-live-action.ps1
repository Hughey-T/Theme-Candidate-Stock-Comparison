[CmdletBinding()]
param(
    [string]$ContainerName = 'theme-compare',
    [string]$Since = '10m'
)

$ErrorActionPreference = 'Stop'

$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCommand) {
    throw 'docker command was not found.'
}

$running = (& docker inspect -f '{{.State.Running}}' $ContainerName 2>$null | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $running -ne 'true') {
    throw "Container is not running: $ContainerName"
}

Write-Host '=== Runtime identity ==='
try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 3
    Write-Host ('Contract: ' + [string]$health.contract_version)
    Write-Host ('Build: ' + [string]$health.build_id)
    $gitHead = (& git rev-parse --short HEAD 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($gitHead)) {
        Write-Host ('Git HEAD: ' + $gitHead)
        if ([string]$health.build_id -eq $gitHead) {
            Write-Host 'Runtime build matches Git HEAD.'
        }
        else {
            $changedFiles = @(& git diff --name-only ([string]$health.build_id + '..HEAD') 2>$null)
            if ($LASTEXITCODE -eq 0 -and $changedFiles.Count -gt 0) {
                $runtimeChanges = @(
                    $changedFiles | Where-Object {
                        $_ -match '^(src/|Dockerfile$|pyproject\.toml$|constraints.*\.txt$)'
                    }
                )
                if ($runtimeChanges.Count -eq 0) {
                    Write-Host 'Runtime build predates Git HEAD only by non-runtime files; runtime code is current.'
                }
                else {
                    Write-Warning 'Runtime build does not include all current runtime-code changes.'
                    Write-Host ('Runtime-impacting files since build: ' + ($runtimeChanges -join ', '))
                }
            }
            else {
                Write-Warning 'Runtime build differs from Git HEAD and the code-impact could not be classified.'
            }
        }
    }
}
catch {
    Write-Warning ('Could not read local runtime health: ' + $_.Exception.Message)
}

$tempStdout = [System.IO.Path]::GetTempFileName()
$tempStderr = [System.IO.Path]::GetTempFileName()
try {
    $process = Start-Process `
        -FilePath $dockerCommand.Source `
        -ArgumentList @('logs', $ContainerName, '--since', $Since, '--timestamps') `
        -NoNewWindow `
        -Wait `
        -PassThru `
        -RedirectStandardOutput $tempStdout `
        -RedirectStandardError $tempStderr

    if ($process.ExitCode -ne 0) {
        throw "Could not read logs from container: $ContainerName (docker exit $($process.ExitCode))"
    }

    $raw = @()
    if ((Get-Item $tempStdout).Length -gt 0) {
        $raw += [System.IO.File]::ReadAllLines($tempStdout)
    }
    if ((Get-Item $tempStderr).Length -gt 0) {
        $raw += [System.IO.File]::ReadAllLines($tempStderr)
    }
}
finally {
    Remove-Item $tempStdout, $tempStderr -Force -ErrorAction SilentlyContinue
}

$entries = @()
foreach ($line in $raw) {
    $text = [string]$line
    # Custom GPT mutating Actions use idempotency_key in the query string.
    # Match both legacy header-based requests (no query) and Action requests
    # without printing the query value, request body, Authorization header, or API key.
    $match = [regex]::Match(
        $text,
        '^(?<timestamp>\S+)\s+.*POST /v2/sessions(?:\?[^ ]*)? HTTP/[0-9.]+"\s+(?<status>\d{3})'
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
    Write-Host 'No query value, request body, Authorization header, or API key was printed.'
    exit 2
}

$recent = @($entries | Sort-Object Timestamp | Select-Object -Last 10)
Write-Host '=== Recent POST /v2/sessions entries ==='
foreach ($entry in $recent) {
    Write-Host ('  ' + $entry.Timestamp + '  HTTP ' + $entry.Status)
}
$latest = $recent[-1]
Write-Host ('Latest status: ' + $latest.Status)

switch ($latest.Status) {
    201 {
        Write-Host 'DIAGNOSIS: a recent session-create request reached the runtime and succeeded.'
        Write-Host 'If the GPT still reported an API error, the next target is Action response handling rather than session creation.'
        exit 0
    }
    401 {
        Write-Host 'DIAGNOSIS: authentication failure. The Custom GPT Action Bearer API key configuration is the next fix target.'
        exit 10
    }
    422 {
        Write-Host 'DIAGNOSIS: authentication succeeded, but the create-session request failed runtime validation.'
        Write-Host 'Next target: request-body or idempotency compatibility diagnostics.'
        exit 20
    }
    default {
        Write-Host ('DIAGNOSIS: runtime returned HTTP ' + $latest.Status + '. Inspect this status before changing the Action schema.')
        exit 30
    }
}
