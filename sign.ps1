# Signiert eine Datei mit Authenticode (SHA-256) und einem RFC3161-Zeitstempel.
# Cert-agnostisch: PFX-Pfad + Passwort als Parameter (lokal) oder via Umgebung
# (CI). Spaeterer Wechsel auf ein OV/EV-Zertifikat = nur PFX/Passwort tauschen.
param(
    [string]$File,
    [string]$Pfx,
    [string]$Password,
    # Comma-separated RFC3161 timestamp servers, tried in order. A single server
    # outage/rate-limit should not fail the whole release, so we fall back.
    [string]$Timestamp = "http://timestamp.digicert.com,http://timestamp.sectigo.com",
    [string]$SignTool
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $File)     { $File     = Join-Path $root 'dist\HaushaltsManager-Setup.exe' }
if (-not $Pfx)      { $Pfx      = Join-Path $root 'cert\HaushaltsManager.pfx' }
if (-not $Password) { $Password = $env:CODESIGN_PFX_PASSWORD }

if (-not (Test-Path $File)) { throw "Datei fehlt: $File" }
if (-not (Test-Path $Pfx))  { throw "PFX fehlt: $Pfx  (zuerst: tools\make-cert.ps1)" }
if (-not $Password)         { throw "Kein PFX-Passwort (Parameter -Password oder Env CODESIGN_PFX_PASSWORD)." }

if (-not $SignTool) {
    $SignTool = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $SignTool) { throw "signtool.exe nicht gefunden (Windows SDK erforderlich)." }

# Try each timestamp server in turn; argument-array (no string concat) so the
# password/paths are passed cleanly.
$tsServers = $Timestamp -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
$signed = $false
foreach ($ts in $tsServers) {
    $signArgs = @(
        'sign', '/fd', 'sha256', '/f', $Pfx, '/p', $Password,
        '/tr', $ts, '/td', 'sha256', '/d', 'HaushaltsManager', $File
    )
    & $SignTool @signArgs
    if ($LASTEXITCODE -eq 0) { $signed = $true; break }
    Write-Host "Zeitstempel-Server fehlgeschlagen ($ts) — versuche naechsten ..."
}
if (-not $signed) { throw "Signieren fehlgeschlagen (alle Zeitstempel-Server, Exit $LASTEXITCODE)." }

& $SignTool verify /pa /v $File
if ($LASTEXITCODE -ne 0) {
    Write-Host "Hinweis: 'verify' meldet nur dann Erfolg, wenn das Zertifikat vertraut wird"
    Write-Host "(self-signed nur auf Rechnern mit hinterlegtem Zertifikat). Signatur selbst ist gesetzt."
}
