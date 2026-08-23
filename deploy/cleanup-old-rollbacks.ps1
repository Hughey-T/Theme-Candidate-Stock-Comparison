[CmdletBinding()]
param(
    [int]$Keep = 1,
    [switch]$Apply,
    [string]$ContainerPrefix = 'theme-compare-rollback-',
    [string]$ImageRepository = 'theme-compare'
)

$ErrorActionPreference = 'Stop'

if ($Keep -lt 1) {
    throw 'Keep must be at least 1.'
}
if ($null -eq (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'docker command was not found.'
}

$generationPattern = '^\d{8}-\d{6}$'
$containerPattern = '^' + [regex]::Escape($ContainerPrefix) + '(\d{8}-\d{6})$'
$imageTagPattern = '^rollback-(\d{8}-\d{6})$'

$containerNames = @(
    & docker ps -a --filter "name=$ContainerPrefix" --format '{{.Names}}' 2>$null |
        ForEach-Object { [string]$_ } |
        Where-Object { $_ -match $containerPattern }
)
if ($LASTEXITCODE -ne 0) {
    throw 'Could not enumerate rollback containers.'
}

$imageRows = @(
    & docker images --filter "reference=$ImageRepository`:rollback-*" --format '{{.Repository}}|{{.Tag}}' 2>$null |
        ForEach-Object { [string]$_ }
)
if ($LASTEXITCODE -ne 0) {
    throw 'Could not enumerate rollback images.'
}

$containerGenerations = @{}
foreach ($name in $containerNames) {
    if ($name -match $containerPattern) {
        $containerGenerations[$Matches[1]] = $name
    }
}

$imageGenerations = @{}
foreach ($row in $imageRows) {
    $parts = $row.Split('|', 2)
    if ($parts.Count -ne 2 -or $parts[0] -ne $ImageRepository) {
        continue
    }
    if ($parts[1] -match $imageTagPattern) {
        $imageGenerations[$Matches[1]] = "$ImageRepository`:$($parts[1])"
    }
}

$generations = @(
    @($containerGenerations.Keys) + @($imageGenerations.Keys) |
        Where-Object { $_ -match $generationPattern } |
        Sort-Object -Descending -Unique
)

if ($generations.Count -eq 0) {
    Write-Host 'No rollback generations were found.'
    exit 0
}

$kept = @($generations | Select-Object -First $Keep)
$targets = @($generations | Select-Object -Skip $Keep)

Write-Host '=== Rollback cleanup plan ==='
Write-Host "Keep generations: $($kept -join ', ')"
if ($targets.Count -eq 0) {
    Write-Host 'Delete generations: <none>'
    Write-Host 'Nothing to clean up.'
    exit 0
}
Write-Host "Delete generations: $($targets -join ', ')"
Write-Host 'Protected resources: current theme-compare container, theme-compare-data volume, local-ai-gateway network.'
Write-Host 'Candidate image tags are not removed by this script.'

$runningTargets = @()
foreach ($generation in $targets) {
    if (-not $containerGenerations.ContainsKey($generation)) {
        continue
    }
    $name = [string]$containerGenerations[$generation]
    $running = (& docker inspect --format '{{.State.Running}}' $name 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect rollback container: $name"
    }
    if ($running -eq 'true') {
        $runningTargets += $name
    }
}
if ($runningTargets.Count -gt 0) {
    throw "Refusing cleanup because target rollback containers are running: $($runningTargets -join ', ')"
}

if (-not $Apply) {
    Write-Host 'DRY RUN ONLY. No Docker object was deleted.'
    Write-Host 'Re-run with -Apply to delete only the listed old rollback containers and rollback image tags.'
    exit 0
}

Write-Host '=== Applying rollback cleanup ==='
foreach ($generation in $targets) {
    if ($containerGenerations.ContainsKey($generation)) {
        $name = [string]$containerGenerations[$generation]
        Write-Host "Removing rollback container: $name"
        & docker rm $name | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to remove rollback container: $name"
        }
    }

    if ($imageGenerations.ContainsKey($generation)) {
        $tag = [string]$imageGenerations[$generation]
        Write-Host "Removing rollback image tag: $tag"
        & docker image rm $tag | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to remove rollback image tag: $tag"
        }
    }
}

Write-Host 'ROLLBACK CLEANUP COMPLETE'
Write-Host "Retained rollback generation(s): $($kept -join ', ')"
Write-Host 'No volume, Docker network, current production container, or candidate image tag was removed.'
