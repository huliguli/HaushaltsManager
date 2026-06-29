# Builds the onedir app and wraps it into the installer dist\HaushaltsManager-Setup.exe
# Usage:  .\build.ps1            (build only)
#         .\build.ps1 -Sign      (also sign the installer with cert\HaushaltsManager.pfx)
param([switch]$Sign)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "Erstelle virtuelle Umgebung (.venv) ..."
    python -m venv .venv
}

Write-Host "Installiere/aktualisiere Abhaengigkeiten ..."
& $py -m pip install --upgrade pip | Out-Null
& $py -m pip install -r requirements.txt

Write-Host "Baue Anwendung (onedir) ..."
& $py -m PyInstaller --noconfirm --clean HaushaltsManager.spec

# Locate ISCC (Inno Setup 6) in the common per-machine / per-user locations.
$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\InnoSetup6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "ISCC.exe (Inno Setup 6) nicht gefunden. Installieren: https://jrsoftware.org/isdl.php" }

$ver = (Get-Content version.json -Raw | ConvertFrom-Json).version
Write-Host "Baue Installer (v$ver) ..."
& $iscc "/DMyAppVersion=$ver" installer\HaushaltsManager.iss

if ($Sign) {
    Write-Host "Signiere Installer ..."
    & .\sign.ps1 -File dist\HaushaltsManager-Setup.exe
}

Write-Host ""
Write-Host "Fertig:  dist\HaushaltsManager-Setup.exe"
