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

function Get-ContainerApiKey {
    param([Parameter(Mandatory = $true)][string]$Name)

    if ($null -eq (Get-Command docker -ErrorAction SilentlyContinue)) {
        return ''
    }

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'SilentlyContinue'
        $json = (& docker inspect $Name --format '{{json .Config.Env}}' 2>$null) -join ''
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    if ($exitCode -ne 0 -or [string]::IsNullOrWhiteSpace($json)) {
        return ''
    }

    try {
        $entries = @($json | ConvertFrom-Json)
    }
    catch {
        return ''
    }

    $prefix = 'THEME_COMPARE_API_KEY='
    $entry = $entries | Where-Object { [string]$_ -like "$prefix*" } | Select-Object -First 1
    if ($null -eq $entry) {
        return ''
    }

    return ([string]$entry).Substring($prefix.Length)
}

Write-Host '=== 1. Configure Theme public URL from the shared Gateway ==='
& $setupNgrok

$existingKey = [string]$env:THEME_COMPARE_API_KEY
$temporaryKey = $false
$plainTextKey = $null
$bstr = [IntPtr]::Zero

try {
    if (-not [string]::IsNullOrWhiteSpace($existingKey)) {
        Write-Host '=== 2. Use existing THEME_COMPARE_API_KEY from this PowerShell session ==='
    }
    else {
        $containerKey = Get-ContainerApiKey -Name $ContainerName
        if (-not [string]::IsNullOrWhiteSpace($containerKey)) {
            Write-Host "=== 2. Reuse API key from running container '$ContainerName' ==="
            Write-Host 'The key is not displayed and is used only for this verifier process.'
            $env:THEME_COMPARE_API_KEY = $containerKey
            $temporaryKey = $true
            $containerKey = $null
        }
        else {
            Write-Host '=== 2. Enter Theme API key ==='
            Write-Host 'No key was available in the current session or runtime container.'
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
