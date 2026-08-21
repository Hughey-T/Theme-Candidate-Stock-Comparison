$ErrorActionPreference = "Stop"

$publicUrl = [string]$env:THEME_COMPARE_PUBLIC_URL
$publicUrl = $publicUrl.TrimEnd('/')
if ([string]::IsNullOrWhiteSpace($publicUrl)) {
    throw "THEME_COMPARE_PUBLIC_URL is required. Run .\deploy\setup-ngrok.ps1 or set a stable HTTPS endpoint explicitly."
}
if ($publicUrl -notmatch '^https://') {
    throw "THEME_COMPARE_PUBLIC_URL must use HTTPS."
}
if ($publicUrl -match 'trycloudflare\.com|example\.(com|org|net)|\.invalid') {
    throw "Ephemeral or placeholder public URLs are forbidden for production."
}

$apiKey = [string]$env:THEME_COMPARE_API_KEY
$apiKey = $apiKey.Trim()
if ([string]::IsNullOrWhiteSpace($apiKey)) {
    throw "THEME_COMPARE_API_KEY is required."
}

$ngrokHeaders = @{ 'ngrok-skip-browser-warning' = '1' }

Write-Host "=== 1. Public readiness ==="
$health = Invoke-RestMethod -Uri "$publicUrl/health" -Headers $ngrokHeaders -UserAgent 'ThemeCompareVerifier/1.0' -TimeoutSec 15
if ($health.service -ne 'ok' -or $health.storage -ne 'ok' -or -not $health.ready) {
    throw "Runtime is not ready."
}
if ($health.contract_version -ne '2.0.0' -or $health.api_profile -ne 'custom-gpt-v2') {
    throw "Runtime contract/profile mismatch."
}
if ([string]::IsNullOrWhiteSpace($health.schema_sha256)) {
    throw "Runtime did not expose schema fingerprint."
}
Write-Host "Runtime ready: contract=$($health.contract_version), build=$($health.build_id)"

Write-Host "=== 2. Unauthenticated request must fail ==="
try {
    Invoke-WebRequest -Uri "$publicUrl/v2/sessions/not-a-session/next-contract" -Headers $ngrokHeaders -UserAgent 'ThemeCompareVerifier/1.0' -TimeoutSec 15 | Out-Null
    throw "Unauthenticated request unexpectedly succeeded."
}
catch {
    if ($null -eq $_.Exception.Response) { throw }
    $status = [int]$_.Exception.Response.StatusCode
    if ($status -ne 401) { throw }
}

Write-Host "=== 3. Generate canonical Action OpenAPI ==="
$actionPath = Join-Path $PSScriptRoot '..\openapi\custom-gpt-action.v2.openapi.json'
python (Join-Path $PSScriptRoot '..\tools\generate_action_openapi.py') `
    --server-url $publicUrl `
    --output $actionPath
if ($LASTEXITCODE -ne 0) { throw "OpenAPI generation failed." }
$action = Get-Content $actionPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($action.paths.PSObject.Properties.Name | Where-Object { $_ -like '/v1/*' }) {
    throw "Generated Action unexpectedly contains v1 paths."
}

Write-Host "=== 4. Create and safely replay a v2 test session ==="
$headers = @{
    Authorization = "Bearer $apiKey"
    'ngrok-skip-browser-warning' = '1'
}
$requestId = "smoke-" + [guid]::NewGuid().ToString('N')
$createHeaders = $headers.Clone()
$createHeaders['Idempotency-Key'] = $requestId
$body = @{
    contract_version = '2.0.0'
    mode = 'standalone'
    theme = 'production-smoke-test'
    analysis_as_of = (Get-Date).ToUniversalTime().ToString('o')
    source_cutoff_at = (Get-Date).ToUniversalTime().AddMinutes(-1).ToString('o')
    candidates = @(@{
        candidate_id = 'US-XNYS-SMOKE-common'
        issuer_id = 'issuer-SMOKE'
        issuer_name = 'Smoke Test Corp'
        ticker = 'SMOKE'
        exchange = 'XNYS'
        share_class = 'common'
        is_adr = $false
        underlying_security_id = $null
        former_tickers = @()
        corporate_action_lineage = @()
        listing_country = 'US'
    })
    horizons = @(@{
        horizon_id = 'medium'
        minimum_months = 12
        maximum_months = 24
        benchmark = 'SPY'
        required_return = 0.10
    })
} | ConvertTo-Json -Depth 20 -Compress

$first = Invoke-RestMethod -Method Post -Uri "$publicUrl/v2/sessions" -Headers $createHeaders -UserAgent 'ThemeCompareVerifier/1.0' -ContentType 'application/json' -Body $body -TimeoutSec 30
$second = Invoke-RestMethod -Method Post -Uri "$publicUrl/v2/sessions" -Headers $createHeaders -UserAgent 'ThemeCompareVerifier/1.0' -ContentType 'application/json' -Body $body -TimeoutSec 30
if (-not $first.accepted -or $first.session_id -ne $second.session_id) {
    throw "Idempotent session replay failed."
}

Write-Host "=== 5. Read next contract ==="
$next = Invoke-RestMethod -Uri "$publicUrl/v2/sessions/$($first.session_id)/next-contract" -Headers $headers -UserAgent 'ThemeCompareVerifier/1.0' -TimeoutSec 15
if ($next.phase -ne 1 -or $next.generation_id -ne 'g1') {
    throw "Unexpected next-contract state."
}

Write-Host "READY: Theme Candidate Stock Comparison v2"
Write-Host "Public URL: $publicUrl"
Write-Host "Action OpenAPI: $actionPath"
Write-Host "Schema SHA-256: $($health.schema_sha256)"
