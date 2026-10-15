# Native PowerShell negative controls for scripts/init.ps1 security validation.

$ErrorActionPreference = "Stop"
if (Test-Path Variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}
$PowerShellPath = (Get-Process -Id $PID).Path
$InitScript = (Resolve-Path (Join-Path $PSScriptRoot "init.ps1")).Path

function Invoke-SecurityValidation([string]$EnvContent) {
    $caseDirectory = Join-Path ([IO.Path]::GetTempPath()) ("yuxi-init-security-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $caseDirectory | Out-Null
    try {
        Set-Content -Path (Join-Path $caseDirectory ".env") -Value $EnvContent -Encoding utf8NoBOM
        Push-Location $caseDirectory
        try {
            & $PowerShellPath -NoProfile -NonInteractive -File $InitScript -ValidateSecurityEnv *> $null
            return $LASTEXITCODE
        } finally {
            Pop-Location
        }
    } finally {
        Remove-Item -LiteralPath $caseDirectory -Recurse -Force
    }
}

function Assert-SecurityValidation([string]$Name, [string]$EnvContent, [bool]$ShouldPass) {
    $exitCode = Invoke-SecurityValidation $EnvContent
    if ($ShouldPass -and $exitCode -ne 0) {
        throw "$Name should pass security validation but exited with $exitCode"
    }
    if (-not $ShouldPass -and $exitCode -eq 0) {
        throw "$Name should fail security validation"
    }
}

function New-SecurityEnv([string]$JwtSecret, [string]$ApiSecret) {
    return @(
        "JWT_SECRET_KEY=$JwtSecret",
        "API_KEY_DERIVATION_SECRET=$ApiSecret"
    ) -join [Environment]::NewLine
}

$validJwt = "jwt-secret-value-that-is-at-least-32-characters"
$validApi = "api-secret-value-that-is-at-least-32-characters"

Assert-SecurityValidation "valid distinct secrets" (New-SecurityEnv $validJwt $validApi) $true
Assert-SecurityValidation "short JWT secret" (New-SecurityEnv "short" $validApi) $false
Assert-SecurityValidation "reused API derivation secret" (New-SecurityEnv $validJwt $validJwt) $false
Assert-SecurityValidation "leading whitespace" (New-SecurityEnv " $validJwt" $validApi) $false
Assert-SecurityValidation "trailing whitespace" (New-SecurityEnv $validJwt "$validApi ") $false
Assert-SecurityValidation "quoted short value" (New-SecurityEnv '"123456789012345678901234567890"' $validApi) $false

Write-Host "PowerShell security environment validation matrix passed."
