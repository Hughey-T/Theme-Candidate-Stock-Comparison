param(
    [switch]$InstallStartupTask
)

$ErrorActionPreference = 'Stop'

function Get-NgrokTunnelUrl {
    try {
        $response = Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 2
    }
    catch {
        return $null
    }

    $httpsTunnel = $response.tunnels |
        Where-Object { $_.public_url -match '^https://' } |
        Select-Object -First 1
    if ($null -eq $httpsTunnel) {
        return $null
    }
    return [string]$httpsTunnel.public_url
}

Write-Host '=== 1. Detect ngrok ==='
$ngrok = Get-Command ngrok -ErrorAction SilentlyContinue
if ($null -eq $ngrok) {
    throw 'ngrok was not found on PATH. Install ngrok, then run this script again.'
}
Write-Host "ngrok: $($ngrok.Source)"
& $ngrok.Source version
if ($LASTEXITCODE -ne 0) {
    throw 'ngrok version check failed.'
}

Write-Host '=== 2. Validate ngrok authentication/config ==='
& $ngrok.Source config check
if ($LASTEXITCODE -ne 0) {
    throw 'ngrok config is not valid. If this machine is not authenticated, run: ngrok config add-authtoken <YOUR_AUTHTOKEN>'
}

Write-Host '=== 3. Validate local runtime ==='
$localHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 5
if ($localHealth.service -ne 'ok' -or $localHealth.storage -ne 'ok' -or -not $localHealth.ready) {
    throw 'Theme Candidate Stock Comparison is not ready on http://127.0.0.1:8000.'
}

Write-Host '=== 4. Start or reuse ngrok endpoint ==='
$publicUrl = Get-NgrokTunnelUrl
if ([string]::IsNullOrWhiteSpace($publicUrl)) {
    $logDir = Join-Path $env:LOCALAPPDATA 'ThemeCandidateStockComparison'
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $stdoutPath = Join-Path $logDir 'ngrok.stdout.log'
    $stderrPath = Join-Path $logDir 'ngrok.stderr.log'

    Start-Process -FilePath $ngrok.Source `
        -ArgumentList @('http', '8000') `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath | Out-Null

    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        $publicUrl = Get-NgrokTunnelUrl
        if (-not [string]::IsNullOrWhiteSpace($publicUrl)) {
            break
        }
    }
}

if ([string]::IsNullOrWhiteSpace($publicUrl)) {
    throw 'ngrok did not expose a public HTTPS endpoint. Check ngrok authentication and logs under %LOCALAPPDATA%\ThemeCandidateStockComparison.'
}
$publicUrl = $publicUrl.TrimEnd('/')
if ($publicUrl -notmatch '^https://') {
    throw "ngrok endpoint is not HTTPS: $publicUrl"
}
if ($publicUrl -match 'trycloudflare\.com|example\.(com|org|net)|\.invalid') {
    throw "Refusing ephemeral or placeholder endpoint: $publicUrl"
}
if ($publicUrl -notmatch '\.ngrok(-free)?\.app$') {
    Write-Warning "Endpoint is not an ngrok-branded development domain: $publicUrl. Verify that it is intentionally stable before importing it into Custom GPT."
}

$env:THEME_COMPARE_PUBLIC_URL = $publicUrl
[Environment]::SetEnvironmentVariable('THEME_COMPARE_PUBLIC_URL', $publicUrl, 'User')
Write-Host "Public URL: $publicUrl"
Write-Host 'Saved THEME_COMPARE_PUBLIC_URL as a user environment variable.'

if ($InstallStartupTask) {
    Write-Host '=== 5. Install current-user startup task ==='
    $taskName = 'ThemeCandidateStockComparison-ngrok'
    $escapedExe = $ngrok.Source.Replace('"', '""')
    $taskCommand = '"' + $escapedExe + '" http 8000'
    schtasks.exe /Create /F /SC ONLOGON /TN $taskName /TR $taskCommand | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to install the ngrok startup task. Re-run PowerShell with sufficient permissions or start ngrok manually.'
    }
    Write-Host "Startup task installed: $taskName"
}

Write-Host '=== 6. Verify public health ==='
$publicHealth = Invoke-RestMethod -Uri "$publicUrl/health" -TimeoutSec 15
if ($publicHealth.service -ne 'ok' -or $publicHealth.storage -ne 'ok' -or -not $publicHealth.ready) {
    throw 'Public ngrok endpoint reached the runtime, but the runtime is not ready.'
}

Write-Host 'NGROK READY'
Write-Host "Next: `$env:THEME_COMPARE_API_KEY = '<secret>'; .\deploy\verify-production.ps1"
