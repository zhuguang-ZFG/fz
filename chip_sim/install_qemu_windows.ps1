# Download Espressif QEMU (Windows x86_64 xtensa) into vendor/espressif_qemu
# Official: https://github.com/espressif/qemu/releases
# Does not add to machine PATH permanently — run_qemu_smoke finds vendor path.

param(
    [string]$Tag = "esp-develop-9.2.2-20260417",
    [string]$Asset = "qemu-xtensa-softmmu-esp_develop_9.2.2_20260417-x86_64-w64-mingw32.tar.xz"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Dest = Join-Path $Root "vendor\espressif_qemu"
$Cache = Join-Path $Dest "download"
New-Item -ItemType Directory -Force -Path $Cache | Out-Null

$Url = "https://github.com/espressif/qemu/releases/download/$Tag/$Asset"
$Tar = Join-Path $Cache $Asset

Write-Host "Download: $Url"
if (-not (Test-Path $Tar)) {
    Invoke-WebRequest -Uri $Url -OutFile $Tar -UseBasicParsing
} else {
    Write-Host "Using cached $Tar"
}

$Extract = Join-Path $Dest "extract"
if (Test-Path $Extract) { Remove-Item -Recurse -Force $Extract }
New-Item -ItemType Directory -Force -Path $Extract | Out-Null

# tar.xz: Windows 10+ tar can extract
Write-Host "Extract to $Extract"
Push-Location $Extract
try {
    tar -xf $Tar
} finally {
    Pop-Location
}

$Exe = Get-ChildItem -Path $Extract -Recurse -Filter "qemu-system-xtensa.exe" | Select-Object -First 1
if (-not $Exe) {
    Write-Error "qemu-system-xtensa.exe not found after extract"
}
$BinLink = Join-Path $Dest "bin"
New-Item -ItemType Directory -Force -Path $BinLink | Out-Null
Copy-Item -Force $Exe.FullName (Join-Path $BinLink "qemu-system-xtensa.exe")
# copy sibling DLLs from same dir
$SrcDir = $Exe.DirectoryName
Get-ChildItem $SrcDir -File | ForEach-Object {
    Copy-Item -Force $_.FullName (Join-Path $BinLink $_.Name)
}
# ROM bios lives under share/qemu — required for -bios / default ROM load
$ShareSrc = Get-ChildItem -Path $Extract -Recurse -Directory -Filter "qemu" |
    Where-Object { Test-Path (Join-Path $_.FullName "esp32-v3-rom.bin") } |
    Select-Object -First 1
if ($ShareSrc) {
    $ShareDst = Join-Path $Dest "share\qemu"
    New-Item -ItemType Directory -Force -Path $ShareDst | Out-Null
    Copy-Item -Force (Join-Path $ShareSrc.FullName "*") $ShareDst
    Write-Host "ROM: $ShareDst\esp32-v3-rom.bin"
}

# Prefer keeping extract/qemu tree intact — run_qemu_smoke uses package root + share/
Write-Host "OK: $($BinLink)\qemu-system-xtensa.exe"
Write-Host "Also keep extract tree: $Extract (share/qemu ROM for default load)"
Write-Host "Next:"
Write-Host "  `$env:ESP_QEMU='$BinLink\qemu-system-xtensa.exe'"
Write-Host "  # better: point at extract package if present"
Write-Host "  `$env:ESP_QEMU=(Get-ChildItem -Recurse $Extract -Filter qemu-system-xtensa.exe | Select -First 1).FullName"
Write-Host "  python chip_sim/build_flash_image.py"
Write-Host "  python chip_sim/run_qemu_smoke.py"
