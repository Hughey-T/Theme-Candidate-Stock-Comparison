[CmdletBinding()]
param(
    [string]$PublicUrl = 'https://remnant-whiff-badly.ngrok-free.dev/theme-compare',
    [string]$ContainerName = 'theme-compare'
)

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$generator = Join-Path $repoRoot 'tools\generate_action_openapi.py'
$output = Join-Path $repoRoot 'openapi\custom-gpt-action.full-schema-diagnostic.openapi.json'
$instructionsPath = Join-Path $repoRoot 'docs\custom-gpt-full-schema-diagnostic-instructions.md'

Write-Host '=== 1. Generate full production Action schema for diagnostic GPT ==='
python $generator --server-url $PublicUrl --output $output
if ($LASTEXITCODE -ne 0) { throw 'Full Action OpenAPI generation failed.' }

$utf8 = New-Object System.Text.UTF8Encoding($false, $true)
$schema = [System.IO.File]::ReadAllText((Resolve-Path $output).Path, $utf8)
if ([string]::IsNullOrWhiteSpace($schema)) { throw 'Full diagnostic Action schema is empty.' }
Set-Clipboard -Value $schema
Write-Host 'FULL DIAGNOSTIC ACTION SCHEMA COPIED'
Write-Host 'Create a NEW temporary Custom GPT distinct from the production GPT.'
Write-Host 'In Actions -> Schema, paste the clipboard contents.'
[void](Read-Host 'After pasting the full Action schema, press Enter to copy the Bearer API key')

Write-Host '=== 2. Copy runtime API key without displaying it ==='
$key = (& docker exec $ContainerName printenv THEME_COMPARE_API_KEY 2>$null | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($key)) {
    throw 'Could not read the runtime API key from the container.'
}
Set-Clipboard -Value $key
Remove-Variable key
Write-Host 'RUNTIME API KEY COPIED (value not displayed)'
Write-Host 'Configure Action Authentication as API Key / Bearer and paste the clipboard value.'
[void](Read-Host 'After configuring Bearer authentication, press Enter to copy the minimal Instructions')

Write-Host '=== 3. Copy minimal full-schema diagnostic Instructions ==='
$instructions = [System.IO.File]::ReadAllText((Resolve-Path $instructionsPath).Path, $utf8)
if ([string]::IsNullOrWhiteSpace($instructions)) { throw 'Full-schema diagnostic Instructions are empty.' }
Set-Clipboard -Value $instructions
Write-Host 'FULL DIAGNOSTIC INSTRUCTIONS COPIED'
Write-Host 'Paste into the temporary GPT main Instructions field and save/update the GPT.'
Write-Host 'Start a NEW conversation with that temporary GPT.'
Write-Host 'First send exactly: CONFIG'
Write-Host 'Expected reply: FULL_SCHEMA_CONFIG_ACTIVE'
Write-Host 'Only if CONFIG passes, then send exactly: RUN'
Write-Host 'Do not modify the production GPT for this diagnostic.'
