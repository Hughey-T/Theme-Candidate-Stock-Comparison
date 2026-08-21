[CmdletBinding()]
param(
    [string]$ContainerName = 'theme-compare',
    [string]$Since = '5m'
)

$ErrorActionPreference = 'Stop'
$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCommand) { throw 'docker command was not found.' }

$running = (& docker inspect -f '{{.State.Running}}' $ContainerName 2>$null | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $running -ne 'true') {
    throw "Container is not running: $ContainerName"
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
    $match = [regex]::Match(
        $text,
        '^(?<timestamp>\S+)\s+.*GET /health\?diagnostic_probe=custom-gpt-diagnostic-v1 HTTP/[0-9.]+"\s+(?<status>\d{3})'
    )
    if ($match.Success) {
        $entries += [pscustomobject]@{
            Timestamp = $match.Groups['timestamp'].Value
            Status = [int]$match.Groups['status'].Value
        }
    }
}

if ($entries.Count -eq 0) {
    Write-Host 'CUSTOM GPT ACTION PROBE: no marked diagnostic GET reached the runtime.'
    Write-Host "Window: $Since"
    Write-Host 'This probe contains no API key, request body, or sensitive query value.'
    exit 2
}

$recent = @($entries | Sort-Object Timestamp | Select-Object -Last 10)
Write-Host '=== Marked Custom GPT Action probe entries ==='
foreach ($entry in $recent) {
    Write-Host ('  ' + $entry.Timestamp + '  GET /health  HTTP ' + $entry.Status)
}
$latest = $recent[-1]
if ($latest.Status -eq 200) {
    Write-Host 'DIAGNOSIS: the temporary Custom GPT invoked the marked Action and the runtime returned HTTP 200.'
    exit 0
}

Write-Host ('DIAGNOSIS: the marked Action reached the runtime but returned HTTP ' + $latest.Status + '.')
exit 10
