# HaushaltsManager

Eine private Desktop-App für **Windows und macOS** zur Verwaltung von Einnahmen,
Fixkosten, variablen Ausgaben und Krediten – mit Dashboard, Fixkosten-Abbau-Timeline,
Finanzierungsrechnern (Annuität, Ballon, Auto, Haus) sowie Excel- und
PDF-Import/-Export. Alle Daten bleiben lokal auf dem Gerät. Beide Plattformen
werden aus **derselben Codebasis** gebaut, sodass der Funktionsumfang identisch bleibt.

> Privat genutztes Werkzeug. Die Oberfläche basiert auf **PyQt6**, das unter der
> **GPL** steht – für die rein private, nicht-kommerzielle Nutzung ist das
> unproblematisch.

## Funktionen

- **Dashboard** – navigierbare Monatsübersicht (Einnahmen / Fixkosten / variabel /
  verbleibend) als Ampel-Cards mit **Vergleich zum Vormonat**, Verfügbarkeits-Kennzahlen,
  **Kategorie-Budgets** (Soll/Ist mit Ampel-Fortschrittsbalken) und einer chronologischen
  **Fixkosten-Abbau-Timeline** (wann fällt welche Kosten weg → neuer Verfügbarkeitsbetrag).
- **Verlauf & Trends** – Einnahmen, Ausgaben und Saldo über 6/12/24 Monate als
  Liniendiagramm, Ausgaben-Kategorien im Zeitverlauf als gestapeltes Balkendiagramm
  und Durchschnitts-Kennzahlen. Speist sich aus den bereits erfassten Daten.
- **Haushaltsbuch** – Einnahmen, Fixkosten-Manager (Kategorien, Enddatum,
  „noch X Monate", Ampel-Farben, Filter) und variable Ausgaben mit Monatsnavigation,
  **monatsübergreifender Suche**, Kategoriefilter und klickbarer Spaltensortierung.
- **Kredite** – laufende Kredite verwalten, optional mit einem Fixkosten-Eintrag
  verknüpft (bleibt synchron).
- **Rechner** – Annuitäten-, Ballon-, Auto- und Hausfinanzierung mit vollständigem
  Tilgungsplan, Standard/Ballon-Vergleich und Haushaltsbudget-Check beim Auto.
- **Sparplaner** – Sparrate ↔ Sparziel mit Zinseszins, Startkapital und Budget-Check.
- **In den Haushalt übernehmen** – berechnete Sparpläne und Kredite lassen sich per
  Klick (mit Bestätigung) ins Haushaltsbuch einplanen: der Sparplan als Fixposten
  über seine Laufzeit – **mit wählbarem Startmonat** (aktueller, nächster oder ein
  beliebiger Zukunftsmonat), sodass genau die betroffenen Monate eingeplant werden –,
  der Kredit als Kredit-Eintrag samt verknüpften Fixkosten. Jederzeit wieder
  rückgängig machbar.
- **Import/Export** – Kontoauszug-Import (CAMT/MT940/CSV/PDF) mit lernender
  Auto-Kategorisierung, Excel-Import mit Spaltenerkennung, PDF-Import mit
  korrigierbarer Vorschau sowie **Excel-Monatsüberblick und PDF-Monatsbericht –
  für den aktuellen oder einen beliebigen vergangenen Monat** (per Monatsauswahl).
- **Datensicherung** – automatische Backups (täglich beim Start sowie vor
  Kontoauszug-Import, Daten-Aktualisierung und Löschen, die letzten 10 werden
  aufbewahrt), manuelles Backup und Ein-Klick-Wiederherstellung in den
  Einstellungen; beim Start wird die Datenbank auf Beschädigung geprüft.
- **Hell-/Dunkel-Design**, deutsche Formate (`1.234,56 €`, `TT.MM.JJJJ`),
  gespeicherte Fenstergröße, automatische Update-Prüfung.

## Installation (Endnutzer)

### Windows

Unter **Releases** die `HaushaltsManager-Setup.exe` herunterladen und ausführen.
Es ist ein **Installer pro Benutzer** (keine Administratorrechte nötig); er legt
die App unter `%LOCALAPPDATA%\Programs\HaushaltsManager` an, erstellt einen
Startmenü-Eintrag und einen Deinstaller. Die Daten liegen separat unter
`%APPDATA%\HaushaltsManager` und werden bei Updates/Deinstallation nicht berührt.

> Hintergrund: Die App wird als Ordner-Build (PyInstaller **onedir**) ausgeliefert
> – die Laufzeit liegt fest neben der `.exe`, es wird nichts mehr nach `%TEMP%`
> entpackt. Das vermeidet die „Failed to load Python DLL"-Fehler, die der frühere
> Einzeldatei-Build (onefile) nach einem Update zeigen konnte.

> Der Installer ist self-signed signiert (Vorabversion). Auf fremden Rechnern kann
> Windows SmartScreen weiterhin warnen – über *Weitere Informationen → Trotzdem
> ausführen*.

### macOS

Unter **Releases** das `HaushaltsManager-macOS.dmg` herunterladen, öffnen und
`HaushaltsManager.app` per Drag-and-drop in den **Programme**-Ordner ziehen. Die
Daten liegen unter `~/Library/Application Support/HaushaltsManager` und bleiben bei
Updates/Deinstallation erhalten.

> Die App ist **ad-hoc signiert** (kostenlos, ohne Apple-Developer-Konto/Notarisierung).
> Beim ersten Start meldet der Gatekeeper einen „unbekannten Entwickler“ – dann per
> **Rechtsklick auf die App → „Öffnen“ → „Öffnen“** einmalig bestätigen (danach startet
> sie normal). Das entspricht der self-signed-Situation unter Windows.

> **Bestehende Windows-Nutzer der v2.3.0:** Weil dieses Release erstmals auch macOS-
> Dateien enthält, kann die automatische Update-Prüfung dieser einen Version die
> Prüfsumme nicht sicher zuordnen und bricht dann sicherheitshalber ab. In dem Fall die
> `HaushaltsManager-Setup.exe` bitte **einmalig manuell** von der Release-Seite laden;
> ab v2.4.0 läuft das Auto-Update wieder normal.

## Eigene Daten vorladen (optional)

Ein frischer Download startet **leer** und führt durch das Quick-Setup. Wer
eigene Daten vorab einlesen möchte, legt eine Datei **`seed.local.json`** in
`%APPDATA%\HaushaltsManager` (oder neben die installierte `.exe`) – nur diese
Datei wird beim ersten Start (leere Datenbank) automatisch geladen. Aufbau/Beispiel
siehe [`database/seed.sample.json`](database/seed.sample.json) (reine Formatvorlage,
wird **nicht** mitgeliefert und **nicht** automatisch geladen).

**Echte Finanzdaten gehören niemals ins Repository** – nur in die lokale,
git-ignorierte `seed.local.json`.

## Aus dem Quellcode bauen

Voraussetzung: Python 3.11+ (entwickelt/getestet mit 3.14) auf Windows.

```powershell
# Einmalig: virtuelle Umgebung + Abhängigkeiten
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# App aus dem Quellcode starten
.\.venv\Scripts\python.exe src\main.py

# Tests
.\.venv\Scripts\python.exe -m pytest -q

# Ordner-Build (onedir) bauen  ->  dist\HaushaltsManager\
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean HaushaltsManager.spec
```

Kürzer geht es mit `build.ps1` – es baut den onedir-Build **und** verpackt ihn mit
**Inno Setup** zum Installer `dist\HaushaltsManager-Setup.exe` (`-Sign` signiert
ihn zusätzlich). `run.ps1` startet aus dem Quellcode. Für den Installer wird
Inno Setup 6 benötigt (<https://jrsoftware.org/isdl.php>).

Auf **macOS** baut `build-mac.sh` aus derselben `.spec` ein `HaushaltsManager.app`,
signiert es ad-hoc und packt es in `dist/HaushaltsManager-macOS.dmg` (nutzt die
Bordmittel `iconutil`/`hdiutil`).

## Update-Mechanismus

Beim Start prüft die App (sofern aktiviert) über die **GitHub-Releases-API**, ob
eine neuere Version vorliegt. Falls ja, erscheint ein nicht-blockierender Dialog
mit den Änderungshinweisen; auf Wunsch lädt die App die zum **eigenen System**
passende Datei herunter, **verifiziert die Prüfsumme** und wendet sie an:

* **Windows:** der signierte Installer läuft **still** (Authenticode-Signatur wird
  vorher gegen einen gepinnten Fingerabdruck geprüft, fail-closed), ersetzt die
  Programmdateien und startet die App neu.
* **macOS:** das `.dmg` wird gemountet und die App tauscht ihr `.app`-Bundle über
  ein kurzes Hilfsskript selbst aus und startet neu. Da die ad-hoc-Signatur keine
  pinbare Identität hat, ist hier die **Prüfsumme Pflicht** (fehlt sie, wird das
  Update sicherheitshalber abgebrochen).

Ohne Internet startet die App normal weiter. Manuelle Prüfung unter
**Einstellungen → Updates**.

Ein neues Release wird über einen Git-Tag/Release angestoßen; der
GitHub-Actions-Workflow [`release.yml`](.github/workflows/release.yml) baut **beide
Plattformen aus derselben Quelle** (100% Parität): macOS (`.dmg`) und Windows
(signierter `.exe`-Installer), je mit `.sha256`.

## Projektstruktur

```
src/
  main.py                  Einstiegspunkt (Logging, Exception-Handling, Start)
  app_meta.py              App-Name, Version, Pfade (%APPDATA%, Ressourcen)
  database/schema.sql      SQLite-Schema (Beträge als Integer-Cent)
  modules/
    money.py  dates.py     Cent-Arithmetik + deutsche Formate/Parser
    config.py  logging_setup.py  seed.py  budget.py  history.py  planning.py
    models.py              Datenmodelle (Dataclasses)
    db_handler/            Datenbank + Repositories (parametrisierte Queries)
    calculator/            Annuität, Ballon, Auto, Haus, Timeline
    file_handler/          Excel-/PDF-Import + Excel-/PDF-Export
    updater/               Update-Prüfung & -Installation (GitHub Releases)
  ui/
    main_window.py  theme.py  icons.py  dialogs.py  wizard.py
    widgets/               Cards, Chart-Canvas, Eingabefelder
    views/                 Dashboard, Haushaltsbuch, Kredite, Rechner, …
tests/                     Unit-Tests (Finanzlogik, Datenbank, Datei-Handler)
database/seed.sample.json  Anonymisierte Beispieldaten (committet)
HaushaltsManager.spec      PyInstaller-Build
```

## Datenschutz

Alle Finanzdaten werden ausschließlich **lokal** in einer SQLite-Datenbank unter
`%APPDATA%\HaushaltsManager` gespeichert. Es findet keine Übertragung an Server
statt; die einzige Netzwerkverbindung ist die optionale Update-Prüfung gegen
GitHub.

## Lizenz

Privates Projekt. Verwendet **PyQt6** (GPL v3). Eine kommerzielle Weitergabe ist
nicht vorgesehen.
