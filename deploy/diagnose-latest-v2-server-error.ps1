[CmdletBinding()]
param(
    [string]$ContainerName = 'theme-compare',
    [string]$Since = '10m'
)

$ErrorActionPreference = 'Stop'

$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCommand) { throw 'docker command was not found.' }

$running = (& docker inspect -f '{{.State.Running}}' $ContainerName 2>$null | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $running -ne 'true') {
    throw "Container is not running: $ContainerName"
}

Write-Host '=== Persisted v2 progress ==='
& (Join-Path $PSScriptRoot 'diagnose-latest-v2-progress.ps1') -ContainerName $ContainerName

Write-Host ''
Write-Host "=== Sanitized server exception log (since $Since) ==="

# Docker writes normal container logs to stderr. In Windows PowerShell 5.1, redirecting
# native stderr through the PowerShell pipeline can turn ordinary log lines into
# NativeCommandError records when ErrorActionPreference=Stop. Capture both streams
# directly from docker.exe instead so INFO lines cannot abort this diagnostic.
$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $dockerCommand.Source
$startInfo.Arguments = "logs --since `"$Since`" --tail 500 `"$ContainerName`""
$startInfo.UseShellExecute = $false
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true
$startInfo.CreateNoWindow = $true

$process = New-Object System.Diagnostics.Process
$process.StartInfo = $startInfo
if (-not $process.Start()) {
    throw 'Could not start docker logs.'
}
$stdoutTask = $process.StandardOutput.ReadToEndAsync()
$stderrTask = $process.StandardError.ReadToEndAsync()
$process.WaitForExit()
$stdout = $stdoutTask.Result
$stderr = $stderrTask.Result
$exitCode = $process.ExitCode
$process.Dispose()

if ($exitCode -ne 0) {
    throw 'Could not read container logs.'
}
$raw = $stdout + [Environment]::NewLine + $stderr

# Never display credentials or idempotency-key values if they appear in a log line.
$sanitized = $raw
$sanitized = [regex]::Replace(
    $sanitized,
    '(?i)(idempotency_key=)[^&\s"'']+',
    '$1<redacted>'
)
$sanitized = [regex]::Replace(
    $sanitized,
    '(?i)(authorization\s*[:=]\s*bearer\s+)[^\s"'']+',
    '$1<redacted>'
)
$sanitized = [regex]::Replace(
    $sanitized,
    '(?i)(THEME_COMPARE_API_KEY\s*[:=]\s*)[^\s"'']+',
    '$1<redacted>'
)

$lines = @($sanitized -split "`r?`n")
$markers = @()
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match 'Exception in ASGI application|Traceback \(most recent call last\)|KeyError|TypeError|AttributeError|ValueError|Internal Server Error') {
        $markers += $i
    }
}

if ($markers.Count -eq 0) {
    Write-Host 'No Python/ASGI exception marker was found in the selected window.'
    Write-Host 'Do not retry the GPT Action yet; rerun with a wider window, for example -Since 30m.'
    return
}

$anchor = $markers[-1]
$start = [Math]::Max(0, $anchor - 8)
$end = [Math]::Min($lines.Count - 1, $anchor + 80)
for ($i = $start; $i -le $end; $i++) {
    $line = $lines[$i]
    if ($line -match '(?i)request body|authorization header|api key') {
        continue
    }
    Write-Host $line
}

Write-Host ''
Write-Host 'Only a bounded, sanitized exception window was printed.'
Write-Host 'No request body, API key, Authorization value, or idempotency-key value should be present.'
