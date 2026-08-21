$ErrorActionPreference = 'Stop'

$setupNgrok = Join-Path $PSScriptRoot 'setup-ngrok.ps1'
$verifyProduction = Join-Path $PSScriptRoot 'verify-production.ps1'

foreach ($script in @($setupNgrok, $verifyProduction)) {
    if (-not (Test-Path $script)) {
        throw "Required deployment script is missing: $script"
    }
}

Write-Host '=== 1. Configure Theme public URL from the shared Gateway ==='
& $setupNgrok

$existingKey = [string]$env:THEME_COMPARE_API_KEY
$temporaryKey = $false
$plainTextKey = $null
$bstr = [IntPtr]::Zero

try {
    if ([string]::IsNullOrWhiteSpace($existingKey)) {
        Write-Host '=== 2. Enter Theme API key ==='
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

            if (-not [string]::IsNullOrWhiteSpace($plainTextKey)) {
                break
            }

            if ($attempt -lt 3) {
                Write-Warning 'API key was empty. Enter the current Theme API key; input remains hidden.'
            }
        }

        if ([string]::IsNullOrWhiteSpace($plainTextKey)) {
            throw 'THEME_COMPARE_API_KEY was empty after 3 attempts.'
        }

        $env:THEME_COMPARE_API_KEY = $plainTextKey
        $temporaryKey = $true
    }
    else {
        Write-Host '=== 2. Use existing THEME_COMPARE_API_KEY from this PowerShell session ==='
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
