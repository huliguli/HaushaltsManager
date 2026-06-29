# Builds the single-file Windows executable into dist\HaushaltsManager.exe
# Usage:  .\build.ps1
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

Write-Host "Baue ausfuehrbare Datei ..."
& $py -m PyInstaller --noconfirm --clean HaushaltsManager.spec

Write-Host ""
Write-Host "Fertig:  dist\HaushaltsManager.exe"
