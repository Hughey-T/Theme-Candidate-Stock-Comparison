param(
    [switch]$InstallStartupTask,
    [int]$GatewayPort = 8080,
    [string]$ServicePrefix = '/theme-compare'
)

$ErrorActionPreference = 'Stop'

function Get-NgrokTunnels {
    try {
        $response = Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 2
    }
    catch {
        return @()
    }
    if ($null -eq $response.tunnels) {
        return @()
    }
    return @($response.tunnels)
}

function Get-NgrokTunnelUrlForPort {
    param(
        [Parameter(Mandatory = $true)][object[]]$Tunnels,
        [Parameter(Mandatory = $true)][int]$Port
    )

    $targetPattern = "^https?://(127\.0\.0\.1|localhost):$Port/?$"
    $httpsTunnel = $Tunnels |
        Where-Object {
            $_.public_url -match '^https://' -and
            [string]$_.config.addr -match $targetPattern
        } |
        Select-Object -First 1

    if ($null -eq $httpsTunnel) {
        return $null
    }
    return [string]$httpsTunnel.public_url
}

function Remove-LegacyThemeNgrokStartup {
    $startupDir = [Environment]::GetFolderPath('Startup')
    if (-not [string]::IsNullOrWhiteSpace($startupDir)) {
        $shortcutPath = Join-Path $startupDir 'ThemeCandidateStockComparison-ngrok.lnk'
        if (Test-Path $shortcutPath) {
            Remove-Item $shortcutPath -Force
            Write-Host "Removed legacy Theme-specific startup shortcut: $shortcutPath"
        }
    }

    $launcherPath = Join-Path $env:LOCALAPPDATA 'ThemeCandidateStockComparison\start-ngrok.ps1'
    if (Test-Path $launcherPath) {
        Remove-Item $launcherPath -Force
        Write-Host "Removed legacy Theme-specific ngrok launcher: $launcherPath"
    }
}

Write-Host '=== 1. Detect ngrok ==='
$ngrok = Get-Command ngrok -ErrorAction SilentlyContinue
if ($null -eq $ngrok) {
    throw 'ngrok was not found on PATH. The shared Local AI Gateway ingress requires the existing ngrok agent.'
}
Write-Host "ngrok: $($ngrok.Source)"
& $ngrok.Source version
if ($LASTEXITCODE -ne 0) {
    throw 'ngrok version check failed.'
}

Write-Host '=== 2. Validate local Theme runtime ==='
$localHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 5
if (
    $localHealth.service -ne 'ok' -or
    $localHealth.storage -ne 'ok' -or
    -not $localHealth.ready -or
    $localHealth.contract_version -ne '2.0.0' -or
    $localHealth.api_profile -ne 'custom-gpt-v2'
) {
    throw 'Theme Candidate Stock Comparison is not ready on http://127.0.0.1:8000.'
}

Write-Host '=== 3. Validate shared Local AI Gateway ==='
$gatewayBase = "http://127.0.0.1:$GatewayPort"
$gatewayHealth = Invoke-RestMethod -Uri "$gatewayBase$ServicePrefix/health" -TimeoutSec 5
if (
    $gatewayHealth.service -ne 'ok' -or
    $gatewayHealth.storage -ne 'ok' -or
    -not $gatewayHealth.ready -or
    $gatewayHealth.contract_version -ne '2.0.0' -or
    $gatewayHealth.api_profile -ne 'custom-gpt-v2'
) {
    throw "Local AI Gateway does not route $ServicePrefix to the Theme Comparison v2 runtime. Run the gateway bootstrap first."
}

Write-Host '=== 4. Detect central ngrok ingress ==='
$tunnels = Get-NgrokTunnels
$publicOrigin = Get-NgrokTunnelUrlForPort -Tunnels $tunnels -Port $GatewayPort
if ([string]::IsNullOrWhiteSpace($publicOrigin)) {
    $summary = ($tunnels | Where-Object { $_.public_url -match '^https://' } | ForEach-Object {
        "$($_.public_url) -> $($_.config.addr)"
    }) -join '; '
    if ([string]::IsNullOrWhiteSpace($summary)) {
        $summary = 'none'
    }
    throw "No central ngrok HTTPS tunnel points to the Local AI Gateway on port $GatewayPort. Existing endpoint(s): $summary. The gateway repository owns ngrok startup; do not start a Theme-specific tunnel."
}

$publicOrigin = $publicOrigin.TrimEnd('/')
if ($publicOrigin -notmatch '^https://') {
    throw "ngrok endpoint is not HTTPS: $publicOrigin"
}
if ($publicOrigin -match 'trycloudflare\.com|example\.(com|org|net)|\.invalid') {
    throw "Refusing ephemeral or placeholder endpoint: $publicOrigin"
}
if ($publicOrigin -notmatch '\.ngrok(-free)?\.(app|dev)$') {
    Write-Warning "Endpoint is not an ngrok-branded development domain: $publicOrigin. Verify that it is intentionally stable before importing it into Custom GPT."
}

$servicePrefixNormalized = '/' + $ServicePrefix.Trim('/')
$publicUrl = "$publicOrigin$servicePrefixNormalized"
$env:THEME_COMPARE_PUBLIC_URL = $publicUrl
[Environment]::SetEnvironmentVariable('THEME_COMPARE_PUBLIC_URL', $publicUrl, 'User')
Write-Host "Public URL: $publicUrl"
Write-Host 'Saved THEME_COMPARE_PUBLIC_URL as a user environment variable.'

Write-Host '=== 5. Remove obsolete Theme-specific ngrok startup ==='
Remove-LegacyThemeNgrokStartup
if ($InstallStartupTask) {
    Write-Warning '-InstallStartupTask is retained only for backward compatibility. ngrok startup is now owned by the shared Local AI Gateway and no Theme-specific startup entry is created.'
}

Write-Host '=== 6. Verify public Theme route ==='
$publicHealth = Invoke-RestMethod -Uri "$publicUrl/health" -TimeoutSec 15
if (
    $publicHealth.service -ne 'ok' -or
    $publicHealth.storage -ne 'ok' -or
    -not $publicHealth.ready -or
    $publicHealth.contract_version -ne '2.0.0' -or
    $publicHealth.api_profile -ne 'custom-gpt-v2' -or
    [string]::IsNullOrWhiteSpace([string]$publicHealth.schema_sha256)
) {
    throw 'Public gateway route reached a runtime, but it does not satisfy the Theme Comparison v2 production health contract.'
}

Write-Host 'NGROK READY'
Write-Host "Next: `$env:THEME_COMPARE_API_KEY = '<secret>'; .\deploy\verify-production.ps1"
