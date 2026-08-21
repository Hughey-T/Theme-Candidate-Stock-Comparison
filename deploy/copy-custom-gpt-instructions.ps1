[CmdletBinding()]
param(
    [string]$InstructionsPath = (Join-Path $PSScriptRoot '..\docs\custom-gpt-production-instructions.md')
)

$ErrorActionPreference = 'Stop'

$resolvedPath = (Resolve-Path -LiteralPath $InstructionsPath).Path
$text = [System.IO.File]::ReadAllText($resolvedPath, [System.Text.Encoding]::UTF8)

if ([string]::IsNullOrWhiteSpace($text)) {
    throw "Custom GPT instructions are empty: $resolvedPath"
}

Set-Clipboard -Value $text

Write-Host 'CUSTOM GPT INSTRUCTIONS COPIED'
Write-Host "Source: $resolvedPath"
Write-Host 'Encoding: UTF-8'
Write-Host 'Paste this into the GPT Builder main Instructions field (replace the entire existing content).'
