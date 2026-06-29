# HaushaltsManager

Eine private Desktop-App für Windows zur Verwaltung von Einnahmen, Fixkosten,
variablen Ausgaben und Krediten – mit Dashboard, Fixkosten-Abbau-Timeline,
Finanzierungsrechnern (Annuität, Ballon, Auto, Haus) sowie Excel- und
PDF-Import/-Export. Alle Daten bleiben lokal auf dem Gerät.

> Privat genutztes Werkzeug. Die Oberfläche basiert auf **PyQt6**, das unter der
> **GPL** steht – für die rein private, nicht-kommerzielle Nutzung ist das
> unproblematisch.

## Funktionen

- **Dashboard** – Monatsübersicht (Einnahmen / Fixkosten / variabel / verbleibend)
  als Ampel-Cards, Verfügbarkeits-Kennzahlen und eine chronologische
  **Fixkosten-Abbau-Timeline** (wann fällt welche Kosten weg → neuer
  Verfügbarkeitsbetrag).
- **Haushaltsbuch** – Einnahmen, Fixkosten-Manager (Kategorien, Enddatum,
  „noch X Monate", Ampel-Farben, Filter) und variable Ausgaben mit Monatsnavigation.
- **Kredite** – laufende Kredite verwalten, optional mit einem Fixkosten-Eintrag
  verknüpft (bleibt synchron).
- **Rechner** – Annuitäten-, Ballon-, Auto- und Hausfinanzierung mit vollständigem
  Tilgungsplan, Standard/Ballon-Vergleich und Haushaltsbudget-Check beim Auto.
- **Import/Export** – Excel-Import mit automatischer Spaltenerkennung (gängige
  Bankexporte), PDF-Import mit korrigierbarer Vorschau, Excel-Export (mehrere
  Tabellenblätter) und PDF-Monatsbericht.
- **Hell-/Dunkel-Design**, deutsche Formate (`1.234,56 €`, `TT.MM.JJJJ`),
  gespeicherte Fenstergröße, automatische Update-Prüfung.

## Installation (Endnutzer)

Unter **Releases** die `HaushaltsManager.exe` herunterladen und starten – fertig.
Es ist keine Installation nötig; die App legt ihre Daten unter
`%APPDATA%\HaushaltsManager` an.

> Die `.exe` ist nicht signiert. Beim ersten Start zeigt Windows SmartScreen ggf.
> „Der Computer wurde geschützt" – über *Weitere Informationen → Trotzdem
> ausführen* startet sie.

## Eigene Daten vorladen (optional)

Beim ersten Start (leere Datenbank) sucht die App nach einer Datei
`seed.local.json` neben der `.exe` oder in `%APPDATA%\HaushaltsManager` und liest
sie ein. Aufbau siehe [`database/seed.sample.json`](database/seed.sample.json).
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

# Einzelne .exe bauen  ->  dist\HaushaltsManager.exe
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean HaushaltsManager.spec
```

Kürzer geht es mit den Helfer-Skripten `build.ps1` (baut die `.exe`) und
`run.ps1` (startet aus dem Quellcode).

## Update-Mechanismus

Beim Start prüft die App (sofern aktiviert) über die **GitHub-Releases-API**, ob
eine neuere Version vorliegt. Falls ja, erscheint ein nicht-blockierender Dialog
mit den Änderungshinweisen; auf Wunsch lädt die App das Update herunter und
startet sich mit ausgetauschter Datei neu. Ohne Internet startet die App ganz
normal weiter. Eine manuelle Prüfung gibt es unter **Einstellungen → Updates**.

Ein neues Release wird über einen Git-Tag/Release angestoßen; der
GitHub-Actions-Workflow [`release.yml`](.github/workflows/release.yml) baut die
`.exe` und hängt sie als Asset an das Release.

## Projektstruktur

```
src/
  main.py                  Einstiegspunkt (Logging, Exception-Handling, Start)
  app_meta.py              App-Name, Version, Pfade (%APPDATA%, Ressourcen)
  database/schema.sql      SQLite-Schema (Beträge als Integer-Cent)
  modules/
    money.py  dates.py     Cent-Arithmetik + deutsche Formate/Parser
    config.py  logging_setup.py  seed.py  budget.py
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
