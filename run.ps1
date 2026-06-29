# Runs the app from source (creates the venv on first use).
# Usage:  .\run.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "Erstelle virtuelle Umgebung (.venv) ..."
    python -m venv .venv
    & $py -m pip install --upgrade pip | Out-Null
    & $py -m pip install -r requirements.txt
}

& $py src\main.py
