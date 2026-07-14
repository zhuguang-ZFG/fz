# Windows one-shot host SIL (grblHAL_sim). Not product silicon.
# Usage: .\scripts\win_full_sim.ps1 [-HwFast] [-WithValidator]
param(
    [switch]$HwFast,
    [switch]$WithValidator,
    [switch]$SkipHardware,
    [switch]$SkipProtocol
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$sim = Join-Path $Root "vendor\grblhal_sim\bin\grblHAL_sim.exe"
if (Test-Path $sim) {
    $env:GRBLHAL_SIM = $sim
    $val = Join-Path $Root "vendor\grblhal_sim\bin\grblHAL_validator.exe"
    if (Test-Path $val) { $env:GRBLHAL_VALIDATOR = $val }
}
$args = @("scripts/win_full_sim.py")
if ($HwFast) { $args += "--hw-fast" }
if ($WithValidator) { $args += "--with-validator" }
if ($SkipHardware) { $args += "--skip-hardware" }
if ($SkipProtocol) { $args += "--skip-protocol" }
& python @args
exit $LASTEXITCODE
