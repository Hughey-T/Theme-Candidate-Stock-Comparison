[CmdletBinding()]
param(
    [string]$PublicUrl = 'https://remnant-whiff-badly.ngrok-free.dev/theme-compare'
)

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$generator = Join-Path $repoRoot 'tools\generate_action_diagnostic_openapi.py'
$output = Join-Path $repoRoot 'openapi\custom-gpt-action.diagnostic.openapi.json'
$instructionsPath = Join-Path $repoRoot 'docs\custom-gpt-action-diagnostic-instructions.md'

Write-Host '=== 1. Generate one-operation unauthenticated diagnostic Action schema ==='
python $generator --server-url $PublicUrl --output $output
if ($LASTEXITCODE -ne 0) { throw 'Diagnostic OpenAPI generation failed.' }

$utf8 = New-Object System.Text.UTF8Encoding($false, $true)
$schema = [System.IO.File]::ReadAllText((Resolve-Path $output).Path, $utf8)
if ([string]::IsNullOrWhiteSpace($schema)) { throw 'Diagnostic Action schema is empty.' }
Set-Clipboard -Value $schema
Write-Host 'DIAGNOSTIC ACTION SCHEMA COPIED'
Write-Host 'Use a NEW temporary Custom GPT.'
Write-Host 'In Actions -> Schema, paste the clipboard contents.'
Write-Host 'Authentication for this diagnostic Action must be None.'
[void](Read-Host 'After pasting the diagnostic Action schema, press Enter to copy the diagnostic Instructions')

Write-Host '=== 2. Copy minimal diagnostic Instructions ==='
$instructions = [System.IO.File]::ReadAllText((Resolve-Path $instructionsPath).Path, $utf8)
if ([string]::IsNullOrWhiteSpace($instructions)) { throw 'Diagnostic Instructions are empty.' }
Set-Clipboard -Value $instructions
Write-Host 'DIAGNOSTIC INSTRUCTIONS COPIED'
Write-Host 'Paste into the temporary GPT main Instructions field and save/update the GPT.'
Write-Host 'Start a NEW conversation with that temporary GPT.'
Write-Host 'First send exactly: CONFIG'
Write-Host 'Expected reply: DIAGNOSTIC_CONFIG_ACTIVE'
Write-Host 'Only if CONFIG passes, then send exactly: RUN'
Write-Host 'Do not modify the production GPT for this diagnostic.'
