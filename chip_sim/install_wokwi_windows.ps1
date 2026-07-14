# Install Wokwi CLI (official) and put %USERPROFILE%\.wokwi\bin on User PATH.
# Docs: https://docs.wokwi.com/wokwi-ci/cli-installation
# Token: https://wokwi.com/dashboard/ci  → set WOKWI_CLI_TOKEN (User env)

$ErrorActionPreference = "Stop"
Write-Host "Installing wokwi-cli via https://wokwi.com/ci/install.ps1 ..."
iwr https://wokwi.com/ci/install.ps1 -useb | iex

$Bin = Join-Path $env:USERPROFILE ".wokwi\bin"
$Exe = Join-Path $Bin "wokwi-cli.exe"
if (-not (Test-Path $Exe)) {
    Write-Error "Install finished but $Exe not found"
}

# Persist User PATH if missing
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$Bin*") {
    [Environment]::SetEnvironmentVariable("Path", ($userPath.TrimEnd(';') + ";" + $Bin), "User")
    Write-Host "Added to User PATH: $Bin (new terminals will see wokwi-cli)"
} else {
    Write-Host "User PATH already contains $Bin"
}
$env:Path = $Bin + ";" + $env:Path

Write-Host ""
Write-Host "CLI: $Exe"
& $Exe --version
Write-Host ""
Write-Host "NEXT — create CI token (required for CLI simulate):"
Write-Host "  1) Open https://wokwi.com/dashboard/ci  (login)"
Write-Host "  2) Create token, then EITHER:"
Write-Host "       [Environment]::SetEnvironmentVariable('WOKWI_CLI_TOKEN','YOUR_TOKEN','User')"
Write-Host "     OR for this session only:"
Write-Host "       `$env:WOKWI_CLI_TOKEN='YOUR_TOKEN'"
Write-Host "  3) cd D:\Users\zhugu\fz"
Write-Host "       `$env:GRBL_ROOT='D:\Users\Grbl_Esp32'"
Write-Host "       python chip_sim/run_wokwi_smoke.py --dry-run"
Write-Host "       python chip_sim/run_wokwi_smoke.py --expect-text 'Grbl'"
Write-Host ""
Write-Host "Browser (no token): https://wokwi.com/"
