[CmdletBinding()]
param(
    [string]$PublicUrl = 'https://remnant-whiff-badly.ngrok-free.dev/theme-compare',
    [string]$ContainerName = 'theme-compare'
)

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$generator = Join-Path $repoRoot 'tools\generate_action_openapi.py'
$output = Join-Path $repoRoot 'openapi\custom-gpt-action.v2.openapi.json'
$instructionsPath = Join-Path $repoRoot 'docs\custom-gpt-production-instructions.md'
$utf8 = New-Object System.Text.UTF8Encoding($false, $true)

Write-Host '=== 1. Generate current full production Action schema ==='
python $generator --server-url $PublicUrl --output $output
if ($LASTEXITCODE -ne 0) { throw 'Production OpenAPI generation failed.' }
$schema = [System.IO.File]::ReadAllText((Resolve-Path $output).Path, $utf8)
if ([string]::IsNullOrWhiteSpace($schema)) { throw 'Production Action schema is empty.' }
Set-Clipboard -Value $schema
Write-Host 'FULL PRODUCTION ACTION SCHEMA COPIED'
Write-Host 'Use the working temporary GPT as a fresh production clone.'
Write-Host 'Replace Actions -> Schema with the clipboard contents.'
[void](Read-Host 'After pasting the full production Action schema, press Enter to copy the Bearer API key')

Write-Host '=== 2. Copy runtime API key without displaying it ==='
$key = (& docker exec $ContainerName printenv THEME_COMPARE_API_KEY 2>$null | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($key)) {
    throw 'Could not read the runtime API key from the container.'
}
Set-Clipboard -Value $key
Remove-Variable key
Write-Host 'RUNTIME API KEY COPIED (value not displayed)'
Write-Host 'Configure Action Authentication as API Key / Bearer and paste the clipboard value.'
[void](Read-Host 'After configuring Bearer authentication, press Enter to copy production Instructions')

Write-Host '=== 3. Copy canonical production Instructions ==='
$instructions = [System.IO.File]::ReadAllText((Resolve-Path $instructionsPath).Path, $utf8)
if ([string]::IsNullOrWhiteSpace($instructions)) { throw 'Production Instructions are empty.' }
Set-Clipboard -Value $instructions
Write-Host 'PRODUCTION INSTRUCTIONS COPIED'
Write-Host 'Replace the temporary GPT main Instructions with the clipboard contents.'
Write-Host 'Enable Web Search capability if it is part of the intended production configuration.'
Write-Host 'Save/update the GPT, start a NEW conversation, and test: GEV-ETN-PWR-VRT'
Write-Host 'Do not change the existing production GPT during this isolation test.'
