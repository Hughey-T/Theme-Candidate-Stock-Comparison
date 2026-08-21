param(
    [string]$ContainerName = 'theme-compare'
)

$ErrorActionPreference = 'Stop'

$setupNgrok = Join-Path $PSScriptRoot 'setup-ngrok.ps1'
$verifyProduction = Join-Path $PSScriptRoot 'verify-production.ps1'

foreach ($script in @($setupNgrok, $verifyProduction)) {
    if (-not (Test-Path $script)) {
        throw "Required deployment script is missing: $script"
    }
}

function Get-EffectiveContainerApiKey {
    param([Parameter(Mandatory = $true)][string]$Name)

    if ($null -eq (Get-Command docker -ErrorAction SilentlyContinue)) {
        return ''
    }

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'SilentlyContinue'
        $lines = @(& docker exec $Name printenv THEME_COMPARE_API_KEY 2>$null)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    if ($exitCode -ne 0 -or $lines.Count -ne 1) {
        return ''
    }
    return [string]$lines[0]
}

function Test-LocalApiKey {
    param([Parameter(Mandatory = $true)][string]$ApiKey)

    if ([string]::IsNullOrWhiteSpace($ApiKey)) {
        return $false
    }

    $headers = @{ Authorization = "Bearer $ApiKey" }
    try {
        Invoke-WebRequest `
            -UseBasicParsing `
            -Uri 'http://127.0.0.1:8000/v2/sessions/not-a-session/next-contract' `
            -Headers $headers `
            -TimeoutSec 10 | Out-Null
        return $true
    }
    catch {
        if ($null -eq $_.Exception.Response) {
            return $false
        }
        $status = [int]$_.Exception.Response.StatusCode
        return ($status -in @(400, 404, 409, 422))
    }
}

Write-Host '=== 1. Configure Theme public URL from the shared Gateway ==='
& $setupNgrok

$existingKey = [string]$env:THEME_COMPARE_API_KEY
$temporaryKey = $false
$plainTextKey = $null
$bstr = [IntPtr]::Zero

try {
    if (-not [string]::IsNullOrWhiteSpace($existingKey) -and (Test-LocalApiKey -ApiKey $existingKey)) {
        Write-Host '=== 2. Use existing THEME_COMPARE_API_KEY from this PowerShell session ==='
        Write-Host 'Local runtime authentication confirmed.'
    }
    else {
        if (-not [string]::IsNullOrWhiteSpace($existingKey)) {
            Write-Warning 'The API key in the current PowerShell session does not authenticate against the local runtime. It will not be used.'
        }

        $containerKey = Get-EffectiveContainerApiKey -Name $ContainerName
        if (-not [string]::IsNullOrWhiteSpace($containerKey) -and (Test-LocalApiKey -ApiKey $containerKey)) {
            Write-Host "=== 2. Reuse effective API key from running container '$ContainerName' ==="
            Write-Host 'Local runtime authentication confirmed. The key is not displayed and is used only for this verifier process.'
            $env:THEME_COMPARE_API_KEY = $containerKey
            $temporaryKey = $true
            $containerKey = $null
        }
        else {
            $containerKey = $null
            Write-Host '=== 2. Enter Theme API key ==='
            Write-Host 'No automatically discovered key authenticated against the local runtime.'
            Write-Host 'Input is hidden and is not written to PowerShell command history.'

            for ($attempt = 1; $attempt -le 3; $attempt++) {
                if ($bstr -ne [IntPtr]::Zero) {
                    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
                    $bstr = [IntPtr]::Zero
                }
                $plainTextKey = $null

                $secureKey = Read-Host 'THEME_COMPARE_API_KEY' -AsSecureString
                $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
                $plainTextKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)

                if ([string]::IsNullOrWhiteSpace($plainTextKey)) {
                    if ($attempt -lt 3) {
                        Write-Warning 'API key was empty. Enter the current Theme API key; input remains hidden.'
                    }
                    continue
                }

                if (Test-LocalApiKey -ApiKey $plainTextKey) {
                    break
                }

                $plainTextKey = $null
                if ($attempt -lt 3) {
                    Write-Warning 'That API key did not authenticate against the local Theme runtime. Try again; input remains hidden.'
                }
            }

            if ([string]::IsNullOrWhiteSpace($plainTextKey)) {
                throw 'No valid THEME_COMPARE_API_KEY was available after automatic discovery and 3 hidden-input attempts.'
            }

            $env:THEME_COMPARE_API_KEY = $plainTextKey
            $temporaryKey = $true
            Write-Host 'Local runtime authentication confirmed.'
        }
    }

    Write-Host '=== 3. Run production verifier ==='
    & $verifyProduction

    Write-Host 'THEME PRODUCTION READY'
    Write-Host "Public URL: $env:THEME_COMPARE_PUBLIC_URL"
    Write-Host 'Next: import openapi/custom-gpt-action.v2.openapi.json into the Theme Custom GPT Action and test a live comparison.'
}
finally {
    if ($bstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    $plainTextKey = $null
    if ($temporaryKey) {
        Remove-Item Env:\THEME_COMPARE_API_KEY -ErrorAction SilentlyContinue
    }
}
