[CmdletBinding()]
param(
    [string]$InspectorUrl = 'http://127.0.0.1:4040/api/requests/http',
    [int]$Limit = 100
)

$ErrorActionPreference = 'Stop'

function Get-HeaderValue {
    param(
        [object]$Headers,
        [string]$Name
    )
    if ($null -eq $Headers) { return $null }
    foreach ($property in $Headers.PSObject.Properties) {
        if ($property.Name -ieq $Name) {
            $value = $property.Value
            if ($value -is [System.Array]) { return ($value -join ', ') }
            return [string]$value
        }
    }
    return $null
}

function Get-StatusCode {
    param([object]$Response)
    if ($null -eq $Response) { return $null }
    if ($null -ne $Response.status_code) { return [int]$Response.status_code }
    if ($null -ne $Response.status) {
        $match = [regex]::Match([string]$Response.status, '^(?<code>\d{3})')
        if ($match.Success) { return [int]$match.Groups['code'].Value }
    }
    return $null
}

function Get-SafePath {
    param([object]$Item)
    $uri = $null
    if ($null -ne $Item.request -and $null -ne $Item.request.uri) {
        $uri = [string]$Item.request.uri
    }
    elseif ($null -ne $Item.uri) {
        $uri = [string]$Item.uri
    }
    if ([string]::IsNullOrWhiteSpace($uri)) { return $null }
    return ($uri -split '\?', 2)[0]
}

function Get-ActionKind {
    param([string]$Path)
    if ($Path -eq '/theme-compare/v2/sessions') { return 'create' }
    if ($Path -eq '/theme-compare/v2/session-create-result') { return 'recovery' }
    if ($Path -match '^/theme-compare/v2/sessions/s_[0-9a-f]{32}/phases$') { return 'phase-submit' }
    return $null
}

try {
    $result = Invoke-RestMethod -Uri ($InspectorUrl + '?limit=' + $Limit) -TimeoutSec 5
}
catch {
    throw ('Could not query the local ngrok inspector at ' + $InspectorUrl + '. ' + $_.Exception.Message)
}

$requests = @($result.requests)
if ($requests.Count -eq 0) {
    Write-Host 'NGROK ACTION RESPONSE DIAGNOSTIC: no inspected HTTP requests are available.'
    exit 2
}

$rows = @()
foreach ($item in $requests) {
    $path = Get-SafePath $item
    $kind = Get-ActionKind $path
    if ($null -eq $kind) { continue }

    $method = if ($null -ne $item.request.method) { [string]$item.request.method } else { '?' }
    $status = Get-StatusCode $item.response
    $headers = $item.response.headers
    $contentType = Get-HeaderValue $headers 'Content-Type'
    $contentLength = Get-HeaderValue $headers 'Content-Length'
    $contentEncoding = Get-HeaderValue $headers 'Content-Encoding'
    $transferEncoding = Get-HeaderValue $headers 'Transfer-Encoding'
    $connection = Get-HeaderValue $headers 'Connection'

    $responseRawLength = $null
    if ($null -ne $item.response.raw) {
        $responseRawLength = ([Text.Encoding]::UTF8.GetByteCount([string]$item.response.raw))
    }

    $rows += [pscustomobject]@{
        Start = [string]$item.start
        Kind = $kind
        Method = $method
        Status = $status
        ContentType = $contentType
        ContentLength = $contentLength
        ContentEncoding = $contentEncoding
        TransferEncoding = $transferEncoding
        Connection = $connection
        RawBytes = $responseRawLength
    }
}

if ($rows.Count -eq 0) {
    Write-Host 'NGROK ACTION RESPONSE DIAGNOSTIC: no recent Theme create/recovery/phase-submit requests were found in the local ngrok inspector.'
    Write-Host 'No request headers, request bodies, query values, API keys, idempotency keys, or session IDs were printed.'
    exit 2
}

$recent = @($rows | Sort-Object Start | Select-Object -Last 20)
Write-Host '=== ngrok-inspected Theme Action responses ==='
foreach ($row in $recent) {
    Write-Host ('  ' + $row.Start + '  ' + $row.Kind + '  ' + $row.Method + '  HTTP ' + $row.Status)
    Write-Host ('    Content-Type: ' + $(if ($row.ContentType) { $row.ContentType } else { '<absent>' }))
    Write-Host ('    Content-Length: ' + $(if ($row.ContentLength) { $row.ContentLength } else { '<absent>' }))
    Write-Host ('    Content-Encoding: ' + $(if ($row.ContentEncoding) { $row.ContentEncoding } else { '<absent>' }))
    Write-Host ('    Transfer-Encoding: ' + $(if ($row.TransferEncoding) { $row.TransferEncoding } else { '<absent>' }))
    Write-Host ('    Connection: ' + $(if ($row.Connection) { $row.Connection } else { '<absent>' }))
    Write-Host ('    Inspector raw response bytes: ' + $(if ($null -ne $row.RawBytes) { $row.RawBytes } else { '<unavailable>' }))
}

$latestSubmit = @($recent | Where-Object Kind -eq 'phase-submit' | Select-Object -Last 1)
if ($latestSubmit.Count -gt 0) {
    $status = $latestSubmit[0].Status
    if ($status -eq 200) {
        Write-Host 'DIAGNOSIS: ngrok observed HTTP 200 for the latest phase submission.'
        Write-Host 'If ChatGPT reported Internal Server Error for that call, the failure is downstream of the ngrok response boundary.'
        exit 0
    }
    if ($status -eq 422) {
        Write-Host 'DIAGNOSIS: ngrok observed HTTP 422 for the latest phase submission.'
        Write-Host 'This is a structured runtime validation failure, not an Internal Server Error.'
        exit 11
    }
    if ($status -eq 500) {
        Write-Host 'DIAGNOSIS: ngrok observed HTTP 500 for the latest phase submission.'
        Write-Host 'Inspect sanitized container logs to identify the server-side exception.'
        exit 12
    }
    Write-Host ('DIAGNOSIS: latest phase submission reached ngrok with HTTP ' + $status + '.')
    Write-Host 'Use the safe response metadata above before changing runtime behavior.'
    exit 13
}

$latestCreate = @($recent | Where-Object Kind -eq 'create' | Select-Object -Last 1)
$latestRecovery = @($recent | Where-Object Kind -eq 'recovery' | Select-Object -Last 1)
if ($latestCreate.Count -gt 0 -and $latestRecovery.Count -gt 0 -and
    $latestCreate[0].Status -eq 200 -and $latestRecovery[0].Status -eq 200) {
    Write-Host 'DIAGNOSIS: ngrok observed HTTP 200 responses for both create and recovery.'
    Write-Host 'If ChatGPT reported transport errors for these calls, the failure is downstream of the ngrok response boundary.'
    exit 0
}

Write-Host 'DIAGNOSIS: no phase submission was observed in the selected inspector window.'
Write-Host 'Use the safe response metadata above before changing runtime behavior.'
exit 10
