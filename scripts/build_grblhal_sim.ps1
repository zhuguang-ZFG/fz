# Rebuild grblHAL_sim into vendor/grblhal_sim/bin (Windows + MinGW + CMake).
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Src = Join-Path $Root "vendor\grblhal_sim\src"
$Build = Join-Path $Root "vendor\grblhal_sim\build"
$Bin = Join-Path $Root "vendor\grblhal_sim\bin"

if (-not (Test-Path (Join-Path $Src "CMakeLists.txt"))) {
    git clone --recurse-submodules https://github.com/grblHAL/Simulator.git $Src
}

New-Item -ItemType Directory -Force -Path $Build, $Bin | Out-Null
cmake -G "MinGW Makefiles" -DCMAKE_C_COMPILER=gcc -DCMAKE_BUILD_TYPE=Release -B $Build -S $Src
cmake --build $Build -j
Copy-Item (Join-Path $Build "grblHAL_sim.exe") $Bin -Force
Copy-Item (Join-Path $Build "grblHAL_validator.exe") $Bin -Force
Write-Host "Installed to $Bin"
