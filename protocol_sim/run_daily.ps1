# Daily protocol regression against vendored grblHAL_sim.
$ErrorActionPreference = "Stop"
$FzRoot = Split-Path $PSScriptRoot -Parent
$env:GRBLHAL_SIM = Join-Path $FzRoot "vendor\grblhal_sim\bin\grblHAL_sim.exe"
$env:GRBLHAL_VALIDATOR = Join-Path $FzRoot "vendor\grblhal_sim\bin\grblHAL_validator.exe"
if (-not (Test-Path $env:GRBLHAL_SIM)) {
    Write-Error "Missing $env:GRBLHAL_SIM — build vendor sim or set GRBLHAL_SIM"
}
Set-Location $FzRoot
python (Join-Path $PSScriptRoot "run_regression.py") --start-sim @args
exit $LASTEXITCODE
