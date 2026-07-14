# Agent vibe gate wrapper (Windows)
param(
    [ValidateSet("auto","quick","standard","deep","firmware")]
    [string]$Profile = "auto",
    [string]$GrblRoot = $env:GRBL_ROOT
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
if (-not $GrblRoot) { $GrblRoot = "D:\Users\Grbl_Esp32" }
if (Test-Path $GrblRoot) { $env:GRBL_ROOT = $GrblRoot }
$sim = Join-Path $Root "vendor\grblhal_sim\bin\grblHAL_sim.exe"
if (Test-Path $sim) { $env:GRBLHAL_SIM = $sim }
& python (Join-Path $Root "scripts\agent_gate.py") --profile $Profile
exit $LASTEXITCODE
