# Code-Signierung

Die `HaushaltsManager.exe` wird mit **Authenticode** (SHA-256) und einem
**RFC3161-Zeitstempel** signiert. Die Signier-Pipeline ist **zertifikat-agnostisch**:
ein Wechsel von einem self-signed auf ein echtes OV/EV-Zertifikat ist nur ein
Austausch der beiden Secrets – kein Code muss geändert werden.

## Ehrliche Einordnung (self-signed)

Aktuell wird ein **selbst-signiertes** Zertifikat verwendet. Das entfernt die
Meldung „Unbekannter Herausgeber" **nur auf Rechnern, die dem Zertifikat
vertrauen** (z. B. der eigene PC, auf dem das Zertifikat im Vertrauensspeicher
liegt). **Fremde Rechner sehen weiterhin eine Windows-SmartScreen-Warnung** –
self-signed schafft kein öffentliches Vertrauen. Für echtes, geräteübergreifendes
Vertrauen ist ein **OV- oder EV-Code-Signing-Zertifikat** einer anerkannten CA nötig.

## Lokal: Zertifikat erstellen & signieren

```powershell
# 1) Self-signed Zertifikat + starkes Zufallspasswort erzeugen (Ausgabe einmalig sichern!)
#    -Trust hinterlegt es zusätzlich lokal, damit signierte Dateien auf DIESEM PC gültig sind.
.\tools\make-cert.ps1 -Trust

# 2) Die gebaute .exe signieren (SHA-256 + RFC3161-Zeitstempel) und prüfen
.\sign.ps1 -File dist\HaushaltsManager.exe -Pfx cert\HaushaltsManager.pfx -Password <pw>

# 3) Signatur prüfen (zeigt Status + Zeitstempel)
&  "C:\Program Files (x86)\Windows Kits\10\bin\<sdk>\x64\signtool.exe" verify /pa /v dist\HaushaltsManager.exe
```

`cert\` (PFX/CER) ist **git-ignoriert** und darf **niemals** committet werden. Das
PFX-Passwort gehört nach `secure.md` (nicht ins Repo).

## CI: automatisches Signieren im Release

Der Workflow [`.github/workflows/release.yml`](.github/workflows/release.yml) baut
die `.exe` und signiert sie, **bevor** die Prüfsumme berechnet wird:

```
Build  →  Sign  →  SHA-256 (über die signierte Datei)  →  Upload (exe + .sha256)
```

Benötigte **GitHub-Actions-Secrets** (Repo-Settings → Secrets and variables → Actions):

| Secret | Inhalt |
| --- | --- |
| `CODESIGN_PFX_BASE64` | Die `.pfx` als Base64 (`[Convert]::ToBase64String([IO.File]::ReadAllBytes("cert\HaushaltsManager.pfx"))`) |
| `CODESIGN_PFX_PASSWORD` | Das PFX-Passwort |

Ist `CODESIGN_PFX_BASE64` nicht gesetzt, **überspringt** der Workflow das Signieren
(der Build bleibt grün, die `.exe` ist dann unsigniert).

## Prüfsummen-Verifikation im Updater

Der In-App-Updater (`src/modules/updater/`) lädt die `.exe` über HTTPS und
**verifiziert sie gegen die mitveröffentlichte `.sha256`**. Stimmt die Prüfsumme
nicht, wird das Update abgebrochen. Deshalb wird die Prüfsumme in der CI **nach**
dem Signieren gebildet (sie muss zur signierten Datei passen).

## Upgrade auf ein echtes Zertifikat (OV/EV)

1. OV/EV-Code-Signing-Zertifikat als `.pfx` beziehen.
2. Die beiden Secrets `CODESIGN_PFX_BASE64` und `CODESIGN_PFX_PASSWORD` ersetzen.
3. Fertig – `sign.ps1` und der Workflow bleiben unverändert.

> EV-Zertifikate liegen oft auf einem Hardware-Token/HSM; dann wird statt einer
> PFX der Token-Provider angesprochen. In dem Fall `sign.ps1`/den CI-Schritt auf
> den jeweiligen Signatur-Provider anpassen.
