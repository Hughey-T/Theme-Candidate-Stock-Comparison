[CmdletBinding()]
param(
    [switch]$ConfigOnly,
    [string]$PublicUrl = 'https://remnant-whiff-badly.ngrok-free.dev/theme-compare',
    [string]$ContainerName = 'theme-compare'
)

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$generator = Join-Path $repoRoot 'tools\generate_action_openapi.py'
$schemaPath = Join-Path $repoRoot 'openapi\custom-gpt-action.v2.openapi.json'
$utf8 = New-Object System.Text.UTF8Encoding($false, $true)

Push-Location $repoRoot
try {
    if ($ConfigOnly) {
        Write-Host '=== 1. Verify current public production runtime ==='
        $health = Invoke-RestMethod -Uri "$PublicUrl/health" -Method Get -TimeoutSec 20
        if ($health.contract_version -ne '2.0.0' -or $health.api_profile -ne 'custom-gpt-v2') {
            throw 'Public production runtime does not expose the expected v2 Custom GPT profile.'
        }
        if ([string]::IsNullOrWhiteSpace([string]$health.schema_sha256)) {
            throw 'Public production runtime did not expose a schema fingerprint.'
        }
        Write-Host "Runtime ready: contract=$($health.contract_version); build=$($health.build)"
    }
    else {
        Write-Host '=== 1. Update production runtime safely ==='
        & (Join-Path $PSScriptRoot 'update-production.ps1')

        Write-Host '=== 2. Finalize and verify public production ==='
        & (Join-Path $PSScriptRoot 'finalize-production.ps1')
    }

    Write-Host '=== 3. Generate and copy canonical Action OpenAPI ==='
    python $generator --server-url $PublicUrl --output $schemaPath
    if ($LASTEXITCODE -ne 0) { throw 'Action OpenAPI generation failed.' }
    $schema = [System.IO.File]::ReadAllText((Resolve-Path $schemaPath).Path, $utf8)
    if ([string]::IsNullOrWhiteSpace($schema)) {
        throw "Action OpenAPI is empty: $schemaPath"
    }
    Set-Clipboard -Value $schema
    Remove-Variable schema
    Write-Host 'CUSTOM GPT ACTION SCHEMA COPIED'
    Write-Host 'In the production GPT Builder: Actions -> Schema -> Ctrl+A -> Ctrl+V.'
    [void](Read-Host 'After pasting the Action schema, press Enter here to copy the Bearer API key')

    Write-Host '=== 4. Copy runtime Bearer API key without displaying it ==='
    $key = (& docker exec $ContainerName printenv THEME_COMPARE_API_KEY 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($key)) {
        throw 'Could not read the runtime API key from the production container.'
    }
    Set-Clipboard -Value $key
    Remove-Variable key
    Write-Host 'RUNTIME API KEY COPIED (value not displayed)'
    Write-Host 'In Action Authentication choose API Key / Bearer and paste the clipboard value.'
    [void](Read-Host 'After configuring Bearer authentication, press Enter here to copy the main Instructions')

    Write-Host '=== 5. Copy canonical production Instructions ==='
    & (Join-Path $PSScriptRoot 'copy-custom-gpt-instructions.ps1')

    Write-Host '=== 6. Production GPT settings and acceptance test ==='
    Write-Host 'Paste the clipboard into the main Instructions field and replace the entire old content.'
    Write-Host 'Capabilities: Web Search = ON (matching the validated test GPT).'
    Write-Host 'No Knowledge attachment is required for the current production protocol.'
    Write-Host 'Save/update the production GPT.'
    Write-Host 'Start a NEW conversation; do not reuse an old production conversation.'
    Write-Host 'Acceptance input: GEV, ETN, PWR, VRT'
    Write-Host 'After each accepted phase, use the normal continuation command: 次'
    Write-Host 'Keep rollback container/image artifacts until this new production conversation completes.'
    Write-Host 'CUSTOM GPT PRODUCTION PROMOTION READY'
}
finally {
    Pop-Location
}
