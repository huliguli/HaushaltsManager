# Erzeugt ein selbst-signiertes Code-Signing-Zertifikat und exportiert es als
# PFX + CER nach cert\.  -Trust legt es zusaetzlich in die Vertrauensspeicher des
# aktuellen Benutzers (ohne Adminrechte), damit auf DIESEM Rechner signierte
# Dateien als gueltig gelten.
#
# Das Skript enthaelt selbst KEIN Geheimnis: ohne -Password wird ein starkes
# Zufallspasswort erzeugt und EINMAL ausgegeben. Passwort sicher ablegen
# (secure.md) und als CI-Secret hinterlegen; PFX/CER NIEMALS committen.
param(
    [string]$Subject  = "CN=HaushaltsManager (Self-Signed)",
    [string]$Password,
    [switch]$Trust
)
$ErrorActionPreference = 'Stop'
$root    = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$certDir = Join-Path $root 'cert'
New-Item -ItemType Directory -Force -Path $certDir | Out-Null
$pfx = Join-Path $certDir 'HaushaltsManager.pfx'
$cer = Join-Path $certDir 'HaushaltsManager.cer'

if (-not $Password) {
    # Safe alphabet (no quotes/spaces) so it round-trips through signtool/secrets.
    $chars = (48..57 + 65..90 + 97..122) | ForEach-Object { [char]$_ }
    $Password = -join (1..28 | ForEach-Object { $chars | Get-Random })
}

$cert = New-SelfSignedCertificate `
    -Type CodeSigningCert `
    -Subject $Subject `
    -KeyAlgorithm RSA -KeyLength 2048 -HashAlgorithm SHA256 `
    -KeyExportPolicy Exportable -KeyUsage DigitalSignature `
    -CertStoreLocation Cert:\CurrentUser\My `
    -NotAfter (Get-Date).AddYears(3)

$sec = ConvertTo-SecureString $Password -AsPlainText -Force
Export-PfxCertificate -Cert $cert -FilePath $pfx -Password $sec | Out-Null
Export-Certificate   -Cert $cert -FilePath $cer | Out-Null

if ($Trust) {
    foreach ($name in 'Root', 'TrustedPublisher') {
        $store = New-Object System.Security.Cryptography.X509Certificates.X509Store($name, 'CurrentUser')
        $store.Open('ReadWrite'); $store.Add($cert); $store.Close()
    }
    "Zertifikat in CurrentUser\Root + TrustedPublisher eingetragen (nur dieser Benutzer)."
}

"PFX:        $pfx"
"Public CER: $cer"
"Thumbprint: $($cert.Thumbprint)"
"Passwort:   $Password"
"-> Passwort in secure.md ablegen und als CI-Secret (CODESIGN_PFX_PASSWORD) setzen."
"-> PFX als Base64 in das CI-Secret CODESIGN_PFX_BASE64 legen; cert\ niemals committen."
