[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $repoRoot
try {
    Write-Host '=== 1. Update production runtime safely ==='
    & (Join-Path $PSScriptRoot 'update-production.ps1')

    Write-Host '=== 2. Finalize and verify public production ==='
    & (Join-Path $PSScriptRoot 'finalize-production.ps1')

    Write-Host '=== 3. Copy Action OpenAPI ==='
    $schemaPath = (Resolve-Path (Join-Path $repoRoot 'openapi\custom-gpt-action.v2.openapi.json')).Path
    $utf8 = New-Object System.Text.UTF8Encoding($false, $true)
    $schema = [System.IO.File]::ReadAllText($schemaPath, $utf8)
    if ([string]::IsNullOrWhiteSpace($schema)) {
        throw "Action OpenAPI is empty: $schemaPath"
    }
    Set-Clipboard -Value $schema
    Write-Host 'CUSTOM GPT ACTION SCHEMA COPIED'
    Write-Host 'In GPT Builder: Actions -> Schema -> Ctrl+A -> Ctrl+V.'
    Write-Host 'Keep the existing API Key / Bearer authentication unchanged.'
    [void](Read-Host 'After pasting the Action schema, press Enter here to copy the main Instructions')

    Write-Host '=== 4. Copy canonical Custom GPT instructions ==='
    & (Join-Path $PSScriptRoot 'copy-custom-gpt-instructions.ps1')

    Write-Host '=== 5. Manual finish ==='
    Write-Host 'In GPT Builder: main Instructions -> Ctrl+A -> Ctrl+V, then save/update the GPT.'
    Write-Host 'Start a NEW conversation and test the four tickers: GEV, ETN, PWR, VRT.'
    Write-Host 'If Phase 1 succeeds, send the normal continuation command used by this GPT.'
    Write-Host 'CUSTOM GPT REFRESH READY'
}
finally {
    Pop-Location
}
