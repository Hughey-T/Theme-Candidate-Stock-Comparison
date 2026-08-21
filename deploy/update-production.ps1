param(
    [string]$ContainerName = 'theme-compare',
    [string]$ImageName = 'theme-compare:latest'
)

$ErrorActionPreference = 'Stop'

function Invoke-Docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    & docker @Args
    if ($LASTEXITCODE -ne 0) {
        throw "docker $($Args -join ' ') failed with exit code $LASTEXITCODE."
    }
}

function Get-ContainerInspect {
    param([string]$Name)
    $json = & docker inspect $Name 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Container '$Name' was not found."
    }
    return (($json -join "`n") | ConvertFrom-Json)[0]
}

function Wait-RuntimeReady {
    param([int]$Attempts = 30)
    for ($i = 0; $i -lt $Attempts; $i++) {
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 3
            if (
                $health.service -eq 'ok' -and
                $health.storage -eq 'ok' -and
                $health.ready -eq $true -and
                $health.contract_version -eq '2.0.0' -and
                $health.api_profile -eq 'custom-gpt-v2' -and
                -not [string]::IsNullOrWhiteSpace([string]$health.schema_sha256)
            ) {
                return $health
            }
        }
        catch {
            # Runtime may still be starting.
        }
        Start-Sleep -Seconds 1
    }
    throw 'New runtime did not satisfy the v2 health contract.'
}

Write-Host '=== 1. Preconditions ==='
$gitStatus = git status --porcelain
if ($LASTEXITCODE -ne 0) {
    throw 'git status failed.'
}
if (-not [string]::IsNullOrWhiteSpace(($gitStatus -join "`n"))) {
    throw 'Working tree has uncommitted changes. Commit/stash them before production update.'
}

$docker = Get-Command docker -ErrorAction SilentlyContinue
if ($null -eq $docker) {
    throw 'docker was not found on PATH.'
}

$old = Get-ContainerInspect -Name $ContainerName
if ($old.State.Running -ne $true) {
    throw "Container '$ContainerName' is not running. Refusing automatic replacement."
}

Write-Host "Current container: $ContainerName"
Write-Host "Current image ID: $($old.Image)"
Write-Host "Restart policy: $($old.HostConfig.RestartPolicy.Name)"

$portBindings = $old.HostConfig.PortBindings.'8000/tcp'
if ($null -eq $portBindings -or $portBindings.Count -ne 1) {
    throw 'Expected exactly one 8000/tcp port binding.'
}
if ([string]$portBindings[0].HostIp -ne '127.0.0.1' -or [string]$portBindings[0].HostPort -ne '8000') {
    throw 'Production runtime must be bound only to 127.0.0.1:8000.'
}

$restartPolicy = [string]$old.HostConfig.RestartPolicy.Name
if ([string]::IsNullOrWhiteSpace($restartPolicy)) {
    $restartPolicy = 'no'
}

$mountArgs = @()
foreach ($mount in $old.Mounts) {
    $mode = if ($mount.RW) { 'rw' } else { 'ro' }
    if ($mount.Type -eq 'volume') {
        if ([string]::IsNullOrWhiteSpace([string]$mount.Name)) {
            throw 'Encountered unnamed volume; refusing automatic replacement.'
        }
        $mountArgs += @('--mount', "type=volume,src=$($mount.Name),dst=$($mount.Destination),$mode")
    }
    elseif ($mount.Type -eq 'bind') {
        $mountArgs += @('--mount', "type=bind,src=$($mount.Source),dst=$($mount.Destination),$mode")
    }
    else {
        throw "Unsupported mount type '$($mount.Type)'."
    }
}
if ($mountArgs.Count -eq 0) {
    throw 'No persistent mount detected. Refusing to replace the runtime.'
}

Write-Host 'Persistent mounts detected:'
foreach ($mount in $old.Mounts) {
    $label = if ($mount.Type -eq 'volume') { $mount.Name } else { $mount.Source }
    Write-Host "  $($mount.Type): $label -> $($mount.Destination)"
}

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$candidateImage = "theme-compare:candidate-$timestamp"
$rollbackImage = "theme-compare:rollback-$timestamp"
$rollbackContainer = "$ContainerName-rollback-$timestamp"
$tempEnv = Join-Path $env:TEMP "theme-compare-env-$([guid]::NewGuid().ToString('N')).txt"
$replacementStarted = $false
$oldRenamed = $false

try {
    Write-Host '=== 2. Build candidate image ==='
    Invoke-Docker build -t $candidateImage .

    Write-Host '=== 3. Preserve rollback image ==='
    Invoke-Docker tag $old.Image $rollbackImage

    # Docker does not retain the original --env-file path. Recreate the effective
    # container environment in a temporary local file without printing values.
    [System.IO.File]::WriteAllLines($tempEnv, [string[]]$old.Config.Env, [System.Text.UTF8Encoding]::new($false))

    Write-Host '=== 4. Stop and preserve old container ==='
    Invoke-Docker stop $ContainerName
    Invoke-Docker rename $ContainerName $rollbackContainer
    $oldRenamed = $true

    Write-Host '=== 5. Start replacement container ==='
    $runArgs = @(
        'run', '-d',
        '--name', $ContainerName,
        '--restart', $restartPolicy,
        '--env-file', $tempEnv,
        '-p', '127.0.0.1:8000:8000'
    )
    $runArgs += $mountArgs
    $runArgs += $candidateImage
    Invoke-Docker @runArgs
    $replacementStarted = $true

    Write-Host '=== 6. Verify v2 health ==='
    $health = Wait-RuntimeReady

    Write-Host '=== 7. Promote candidate image ==='
    Invoke-Docker tag $candidateImage $ImageName

    Write-Host "Rollback container retained (stopped): $rollbackContainer"
    Write-Host "Rollback image retained: $rollbackImage"
    Write-Host "Contract: $($health.contract_version); build=$($health.build_id)"
    Write-Host 'RUNTIME READY: Theme Candidate Stock Comparison v2'
}
catch {
    $failure = $_
    Write-Warning "Production update failed: $($failure.Exception.Message)"

    if ($replacementStarted) {
        & docker rm -f $ContainerName | Out-Null
    }

    if ($oldRenamed) {
        & docker rename $rollbackContainer $ContainerName | Out-Null
        if ($LASTEXITCODE -eq 0) {
            & docker start $ContainerName | Out-Null
        }
    }

    & docker tag $rollbackImage $ImageName 2>$null | Out-Null
    Write-Warning 'Rollback attempted. Verify http://127.0.0.1:8000/health before retrying.'
    throw
}
finally {
    if (Test-Path $tempEnv) {
        Remove-Item $tempEnv -Force -ErrorAction SilentlyContinue
    }
}
