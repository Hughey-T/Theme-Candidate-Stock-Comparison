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

    $create = [regex]::Match(
        $text,
        '^(?<timestamp>\S+)\s+.*POST /v2/sessions(?:\?[^ ]*)? HTTP/[0-9.]+"\s+(?<status>\d{3})'
    )
    if ($create.Success) {
        $entries += [pscustomobject]@{
            Timestamp = $create.Groups['timestamp'].Value
            Operation = 'create'
            Method = 'POST'
            Status = [int]$create.Groups['status'].Value
        }
        continue
    }

    $recovery = [regex]::Match(
        $text,
        '^(?<timestamp>\S+)\s+.*GET /v2/session-create-result(?:\?[^ ]*)? HTTP/[0-9.]+"\s+(?<status>\d{3})'
    )
    if ($recovery.Success) {
        $entries += [pscustomobject]@{
            Timestamp = $recovery.Groups['timestamp'].Value
            Operation = 'recovery'
            Method = 'GET'
            Status = [int]$recovery.Groups['status'].Value
        }
    }
}

if ($entries.Count -eq 0) {
    Write-Host 'LIVE ACTION DIAGNOSTIC: no recent create or recovery Action reached the runtime.'
    Write-Host "Window: $Since"
    Write-Host 'No query value, request body, Authorization header, or API key was printed.'
    exit 2
}

$recent = @($entries | Sort-Object Timestamp | Select-Object -Last 20)
Write-Host '=== Recent create/recovery Action entries ==='
foreach ($entry in $recent) {
    Write-Host ('  ' + $entry.Timestamp + '  ' + $entry.Operation + '  ' + $entry.Method + '  HTTP ' + $entry.Status)
}

$latestCreate = @($recent | Where-Object { $_.Operation -eq 'create' } | Select-Object -Last 1)
$latestRecovery = @($recent | Where-Object { $_.Operation -eq 'recovery' } | Select-Object -Last 1)

if ($latestCreate.Count -gt 0) {
    Write-Host ('Latest create status: ' + $latestCreate[0].Status)
}
else {
    Write-Host 'Latest create status: not observed'
}
if ($latestRecovery.Count -gt 0) {
    Write-Host ('Latest recovery status: ' + $latestRecovery[0].Status)
}
else {
    Write-Host 'Latest recovery status: not observed'
}

if (
    $latestCreate.Count -gt 0 -and
    $latestRecovery.Count -gt 0 -and
    $latestCreate[0].Status -eq 200 -and
    $latestRecovery[0].Status -eq 200
) {
    Write-Host 'DIAGNOSIS: both create and recovery reached the runtime and succeeded with HTTP 200.'
    Write-Host 'If the GPT reported transport errors for both, the remaining failure is after runtime response generation.'
    exit 0
}

if ($latestCreate.Count -gt 0 -and $latestCreate[0].Status -eq 201) {
    Write-Host 'DIAGNOSIS: create succeeded, but the runtime still uses legacy HTTP 201. Refresh production first.'
    exit 5
}

foreach ($entry in @($latestCreate + $latestRecovery)) {
    if ($entry.Count -eq 0) { continue }
    switch ($entry.Status) {
        401 {
            Write-Host ('DIAGNOSIS: ' + $entry.Operation + ' authentication failed with HTTP 401.')
            exit 10
        }
        404 {
            if ($entry.Operation -eq 'recovery') {
                Write-Host 'DIAGNOSIS: recovery reached the runtime, but no completed create result was found for that idempotency key.'
                exit 15
            }
        }
        422 {
            Write-Host ('DIAGNOSIS: ' + $entry.Operation + ' reached the runtime but failed validation with HTTP 422.')
            exit 20
        }
    }
    if ($entry.Status -ge 500) {
        Write-Host ('DIAGNOSIS: ' + $entry.Operation + ' returned server error HTTP ' + $entry.Status + '.')
        exit 30
    }
}

Write-Host 'DIAGNOSIS: create/recovery reached the runtime, but the observed status combination needs inspection.'
exit 40
