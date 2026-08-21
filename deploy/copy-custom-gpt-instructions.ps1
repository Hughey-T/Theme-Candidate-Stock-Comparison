[CmdletBinding()]
param(
    [string]$InstructionsPath = (Join-Path $PSScriptRoot '..\docs\custom-gpt-production-instructions.md'),
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'

$resolvedPath = (Resolve-Path -LiteralPath $InstructionsPath).Path
$text = [System.IO.File]::ReadAllText($resolvedPath, [System.Text.Encoding]::UTF8)

if ([string]::IsNullOrWhiteSpace($text)) {
    throw "Custom GPT instructions are empty: $resolvedPath"
}
if ($text -notmatch 'このGPTは') {
    throw 'UTF-8 Japanese instruction text was not decoded correctly.'
}
if ($text -match '縺|窶') {
    throw 'Detected mojibake markers in Custom GPT instructions.'
}

if ($ValidateOnly) {
    Write-Host 'CUSTOM GPT INSTRUCTIONS UTF-8 VALID'
    Write-Host "Source: $resolvedPath"
    return
}

Set-Clipboard -Value $text

Write-Host 'CUSTOM GPT INSTRUCTIONS COPIED'
Write-Host "Source: $resolvedPath"
Write-Host 'Encoding: UTF-8'
Write-Host 'Paste this into the GPT Builder main Instructions field (replace the entire existing content).'
