[CmdletBinding()]
param(
    [string]$InstructionsPath = (Join-Path $PSScriptRoot '..\docs\custom-gpt-production-instructions.md'),
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'

$resolvedPath = (Resolve-Path -LiteralPath $InstructionsPath).Path
$utf8 = New-Object System.Text.UTF8Encoding($false, $true)
$text = [System.IO.File]::ReadAllText($resolvedPath, $utf8)

if ([string]::IsNullOrWhiteSpace($text)) {
    throw "Custom GPT instructions are empty: $resolvedPath"
}
if ($text -notmatch 'contract 2\.0' -or $text -notmatch 'createBlindComparisonSessionV2') {
    throw 'Expected v2 instruction markers were not found.'
}
if ($text.IndexOf([char]0xFFFD) -ge 0) {
    throw 'Unicode replacement characters were found in Custom GPT instructions.'
}

$hasJapanese = $false
foreach ($ch in $text.ToCharArray()) {
    $code = [int][char]$ch
    if (($code -ge 0x3040 -and $code -le 0x30FF) -or ($code -ge 0x4E00 -and $code -le 0x9FFF)) {
        $hasJapanese = $true
        break
    }
}
if (-not $hasJapanese) {
    throw 'No Japanese characters were found after strict UTF-8 decoding.'
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
