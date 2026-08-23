[CmdletBinding()]
param(
    [int]$Keep = 1,
    [switch]$Apply,
    [string]$ContainerPrefix = 'theme-compare-rollback-',
    [string]$CurrentContainerName = 'theme-compare',
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
$rollbackTagPattern = '^rollback-(\d{8}-\d{6})$'
$candidateTagPattern = '^candidate-(\d{8}-\d{6})$'

function Get-ImageIdForTag {
    param([Parameter(Mandatory = $true)][string]$Tag)

    $id = (& docker image inspect --format '{{.Id}}' $Tag 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($id)) {
        throw "Could not inspect image tag: $Tag"
    }
    return $id
}

function Get-ContainerImageId {
    param([Parameter(Mandatory = $true)][string]$Name)

    $id = (& docker inspect --format '{{.Image}}' $Name 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($id)) {
        throw "Could not inspect container image: $Name"
    }
    return $id
}

$containerNames = @(
    & docker ps -a --filter "name=$ContainerPrefix" --format '{{.Names}}' 2>$null |
        ForEach-Object { [string]$_ } |
        Where-Object { $_ -match $containerPattern }
)
if ($LASTEXITCODE -ne 0) {
    throw 'Could not enumerate rollback containers.'
}

$rollbackImageRows = @(
    & docker images --filter "reference=$ImageRepository`:rollback-*" --format '{{.Repository}}|{{.Tag}}' 2>$null |
        ForEach-Object { [string]$_ }
)
if ($LASTEXITCODE -ne 0) {
    throw 'Could not enumerate rollback images.'
}

$candidateImageRows = @(
    & docker images --filter "reference=$ImageRepository`:candidate-*" --format '{{.Repository}}|{{.Tag}}' 2>$null |
        ForEach-Object { [string]$_ }
)
if ($LASTEXITCODE -ne 0) {
    throw 'Could not enumerate candidate images.'
}

$containerGenerations = @{}
foreach ($name in $containerNames) {
    if ($name -match $containerPattern) {
        $containerGenerations[$Matches[1]] = $name
    }
}

$rollbackImageGenerations = @{}
foreach ($row in $rollbackImageRows) {
    $parts = $row.Split('|', 2)
    if ($parts.Count -ne 2 -or $parts[0] -ne $ImageRepository) {
        continue
    }
    if ($parts[1] -match $rollbackTagPattern) {
        $rollbackImageGenerations[$Matches[1]] = "$ImageRepository`:$($parts[1])"
    }
}

$generations = @(
    @($containerGenerations.Keys) + @($rollbackImageGenerations.Keys) |
        Where-Object { $_ -match $generationPattern } |
        Sort-Object -Descending -Unique
)

$kept = @($generations | Select-Object -First $Keep)
$rollbackTargets = @($generations | Select-Object -Skip $Keep)
$rollbackTargetContainerNames = @(
    foreach ($generation in $rollbackTargets) {
        if ($containerGenerations.ContainsKey($generation)) {
            [string]$containerGenerations[$generation]
        }
    }
)

$runningTargets = @()
foreach ($name in $rollbackTargetContainerNames) {
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

$protectedImageIds = @{}
$allContainerNames = @(
    & docker ps -a --format '{{.Names}}' 2>$null |
        ForEach-Object { [string]$_ } |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
)
if ($LASTEXITCODE -ne 0) {
    throw 'Could not enumerate containers for image protection.'
}
foreach ($name in $allContainerNames) {
    if ($rollbackTargetContainerNames -contains $name) {
        continue
    }
    $protectedImageIds[(Get-ContainerImageId -Name $name)] = $true
}

foreach ($generation in $kept) {
    if ($rollbackImageGenerations.ContainsKey($generation)) {
        $protectedImageIds[(Get-ImageIdForTag -Tag ([string]$rollbackImageGenerations[$generation]))] = $true
    }
}

$currentExists = @(& docker ps -a --filter "name=^/$CurrentContainerName$" --format '{{.Names}}' 2>$null)
if ($LASTEXITCODE -ne 0) {
    throw "Could not verify current production container: $CurrentContainerName"
}
if ($currentExists -contains $CurrentContainerName) {
    $protectedImageIds[(Get-ContainerImageId -Name $CurrentContainerName)] = $true
}

$candidateTags = @()
foreach ($row in $candidateImageRows) {
    $parts = $row.Split('|', 2)
    if ($parts.Count -ne 2 -or $parts[0] -ne $ImageRepository) {
        continue
    }
    if ($parts[1] -match $candidateTagPattern) {
        $candidateTags += "$ImageRepository`:$($parts[1])"
    }
}
$candidateTags = @($candidateTags | Sort-Object -Unique)

$protectedCandidateTags = @()
$candidateTargets = @()
foreach ($tag in $candidateTags) {
    $imageId = Get-ImageIdForTag -Tag $tag
    if ($protectedImageIds.ContainsKey($imageId)) {
        $protectedCandidateTags += $tag
    }
    else {
        $candidateTargets += $tag
    }
}

Write-Host '=== Docker cleanup plan ==='
if ($kept.Count -gt 0) {
    Write-Host "Keep rollback generations: $($kept -join ', ')"
}
else {
    Write-Host 'Keep rollback generations: <none found>'
}
if ($rollbackTargets.Count -gt 0) {
    Write-Host "Delete rollback generations: $($rollbackTargets -join ', ')"
}
else {
    Write-Host 'Delete rollback generations: <none>'
}
if ($protectedCandidateTags.Count -gt 0) {
    Write-Host "Protected candidate tags: $($protectedCandidateTags -join ', ')"
}
else {
    Write-Host 'Protected candidate tags: <none>'
}
if ($candidateTargets.Count -gt 0) {
    Write-Host "Delete unreferenced candidate tags: $($candidateTargets -join ', ')"
}
else {
    Write-Host 'Delete unreferenced candidate tags: <none>'
}
Write-Host 'Protected resources: current theme-compare container, surviving containers, retained rollback generation(s), theme-compare-data volume, local-ai-gateway network.'
Write-Host 'No Docker prune command is used.'

if ($rollbackTargets.Count -eq 0 -and $candidateTargets.Count -eq 0) {
    Write-Host 'Nothing to clean up.'
    exit 0
}

if (-not $Apply) {
    Write-Host 'DRY RUN ONLY. No Docker object was deleted.'
    Write-Host 'Re-run with -Apply to delete only the listed old rollback objects and unreferenced candidate tags.'
    exit 0
}

Write-Host '=== Applying Docker cleanup ==='
foreach ($generation in $rollbackTargets) {
    if ($containerGenerations.ContainsKey($generation)) {
        $name = [string]$containerGenerations[$generation]
        Write-Host "Removing rollback container: $name"
        & docker rm $name | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to remove rollback container: $name"
        }
    }

    if ($rollbackImageGenerations.ContainsKey($generation)) {
        $tag = [string]$rollbackImageGenerations[$generation]
        Write-Host "Removing rollback image tag: $tag"
        & docker image rm $tag | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to remove rollback image tag: $tag"
        }
    }
}

foreach ($tag in $candidateTargets) {
    Write-Host "Removing unreferenced candidate image tag: $tag"
    & docker image rm $tag | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to remove candidate image tag: $tag"
    }
}

Write-Host 'DOCKER CLEANUP COMPLETE'
if ($kept.Count -gt 0) {
    Write-Host "Retained rollback generation(s): $($kept -join ', ')"
}
Write-Host 'Current production container, surviving container images, retained rollback images, volume, and Docker network were preserved.'
