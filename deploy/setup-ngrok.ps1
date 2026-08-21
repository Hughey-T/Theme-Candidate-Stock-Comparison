param(
    [switch]$InstallStartupTask
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

function Install-NgrokStartupShortcut {
    param(
        [Parameter(Mandatory = $true)][string]$NgrokPath
    )

    $appDir = Join-Path $env:LOCALAPPDATA 'ThemeCandidateStockComparison'
    New-Item -ItemType Directory -Path $appDir -Force | Out-Null

    $launcherPath = Join-Path $appDir 'start-ngrok.ps1'
    $stdoutPath = Join-Path $appDir 'ngrok.stdout.log'
    $stderrPath = Join-Path $appDir 'ngrok.stderr.log'

    $ngrokLiteral = $NgrokPath.Replace("'", "''")
    $stdoutLiteral = $stdoutPath.Replace("'", "''")
    $stderrLiteral = $stderrPath.Replace("'", "''")
    $launcher = @"
`$ErrorActionPreference = 'SilentlyContinue'
try {
    `$response = Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 2
    `$existing = `$response.tunnels | Where-Object {
        `$_.public_url -match '^https://' -and
        [string]`$_.config.addr -match '^https?://(127\.0\.0\.1|localhost):8000/?$'
    } | Select-Object -First 1
    if (`$null -ne `$existing) {
        exit 0
    }
    if (`$null -ne (`$response.tunnels | Where-Object { `$_.public_url -match '^https://' } | Select-Object -First 1)) {
        exit 2
    }
}
catch {
}
Start-Process -FilePath '$ngrokLiteral' -ArgumentList @('http', '8000') -WindowStyle Hidden -RedirectStandardOutput '$stdoutLiteral' -RedirectStandardError '$stderrLiteral' | Out-Null
"@
    Set-Content -LiteralPath $launcherPath -Value $launcher -Encoding UTF8

    $startupDir = [Environment]::GetFolderPath('Startup')
    if ([string]::IsNullOrWhiteSpace($startupDir)) {
        throw 'Windows Startup folder could not be resolved.'
    }

    $powershell = (Get-Command powershell.exe -ErrorAction Stop).Source
    $shortcutPath = Join-Path $startupDir 'ThemeCandidateStockComparison-ngrok.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $powershell
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launcherPath`""
    $shortcut.WorkingDirectory = $appDir
    $shortcut.WindowStyle = 7
    $shortcut.Save()

    Write-Host "Startup shortcut installed: $shortcutPath"
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
$tunnels = Get-NgrokTunnels
$publicUrl = Get-NgrokTunnelUrlForPort -Tunnels $tunnels -Port 8000

if ([string]::IsNullOrWhiteSpace($publicUrl)) {
    $otherHttps = $tunnels | Where-Object { $_.public_url -match '^https://' }
    if ($otherHttps.Count -gt 0) {
        $summary = ($otherHttps | ForEach-Object { "$($_.public_url) -> $($_.config.addr)" }) -join '; '
        throw "No ngrok HTTPS tunnel points to Theme Comparison on port 8000. Existing endpoint(s): $summary. Do not reuse another service's endpoint. On ngrok Free, the account development domain may already be occupied; use a separate stable domain/paid ngrok domain or another stable ingress."
    }

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
        $tunnels = Get-NgrokTunnels
        $publicUrl = Get-NgrokTunnelUrlForPort -Tunnels $tunnels -Port 8000
        if (-not [string]::IsNullOrWhiteSpace($publicUrl)) {
            break
        }
    }
}

if ([string]::IsNullOrWhiteSpace($publicUrl)) {
    throw 'ngrok did not expose a public HTTPS endpoint for http://127.0.0.1:8000. Check ngrok account limits and logs under %LOCALAPPDATA%\ThemeCandidateStockComparison.'
}
$publicUrl = $publicUrl.TrimEnd('/')
if ($publicUrl -notmatch '^https://') {
    throw "ngrok endpoint is not HTTPS: $publicUrl"
}
if ($publicUrl -match 'trycloudflare\.com|example\.(com|org|net)|\.invalid') {
    throw "Refusing ephemeral or placeholder endpoint: $publicUrl"
}
if ($publicUrl -notmatch '\.ngrok(-free)?\.(app|dev)$') {
    Write-Warning "Endpoint is not an ngrok-branded development domain: $publicUrl. Verify that it is intentionally stable before importing it into Custom GPT."
}

$env:THEME_COMPARE_PUBLIC_URL = $publicUrl
[Environment]::SetEnvironmentVariable('THEME_COMPARE_PUBLIC_URL', $publicUrl, 'User')
Write-Host "Public URL: $publicUrl"
Write-Host 'Saved THEME_COMPARE_PUBLIC_URL as a user environment variable.'

if ($InstallStartupTask) {
    Write-Host '=== 5. Install current-user startup ==='
    Install-NgrokStartupShortcut -NgrokPath $ngrok.Source
}

Write-Host '=== 6. Verify public health ==='
$publicHealth = Invoke-RestMethod -Uri "$publicUrl/health" -TimeoutSec 15
if (
    $publicHealth.service -ne 'ok' -or
    $publicHealth.storage -ne 'ok' -or
    -not $publicHealth.ready -or
    $publicHealth.contract_version -ne '2.0.0' -or
    $publicHealth.api_profile -ne 'custom-gpt-v2' -or
    [string]::IsNullOrWhiteSpace([string]$publicHealth.schema_sha256)
) {
    throw 'Public ngrok endpoint reached the runtime, but the runtime does not satisfy the v2 production health contract.'
}

Write-Host 'NGROK READY'
Write-Host "Next: `$env:THEME_COMPARE_API_KEY = '<secret>'; .\deploy\verify-production.ps1"
