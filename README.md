# HaushaltsManager

Eine private Desktop-App für Windows zur Verwaltung von Einnahmen, Fixkosten,
variablen Ausgaben und Krediten – mit Dashboard, Fixkosten-Abbau-Timeline,
Finanzierungsrechnern (Annuität, Ballon, Auto, Haus) sowie Excel- und
PDF-Import/-Export. Alle Daten bleiben lokal auf dem Gerät.

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
- **Import/Export** – Kontoauszug-Import (CAMT/MT940/CSV/PDF) mit lernender
  Auto-Kategorisierung, Excel-Import mit Spaltenerkennung, PDF-Import mit
  korrigierbarer Vorschau, Excel-Export (mehrere Tabellenblätter) und PDF-Monatsbericht.
- **Hell-/Dunkel-Design**, deutsche Formate (`1.234,56 €`, `TT.MM.JJJJ`),
  gespeicherte Fenstergröße, automatische Update-Prüfung.

## Installation (Endnutzer)

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

## Update-Mechanismus

Beim Start prüft die App (sofern aktiviert) über die **GitHub-Releases-API**, ob
eine neuere Version vorliegt. Falls ja, erscheint ein nicht-blockierender Dialog
mit den Änderungshinweisen; auf Wunsch lädt die App den **signierten Installer**
herunter, **verifiziert die Prüfsumme** und führt ihn **still** aus – der
Installer ersetzt die Programmdateien und startet die App neu. Ohne Internet
startet die App ganz normal weiter. Manuelle Prüfung unter **Einstellungen → Updates**.

Ein neues Release wird über einen Git-Tag/Release angestoßen; der
GitHub-Actions-Workflow [`release.yml`](.github/workflows/release.yml) baut den
onedir-Build, schnürt den Installer, **signiert** ihn und hängt
`HaushaltsManager-Setup.exe` + `.sha256` ans Release.

## Projektstruktur

```
src/
  main.py                  Einstiegspunkt (Logging, Exception-Handling, Start)
  app_meta.py              App-Name, Version, Pfade (%APPDATA%, Ressourcen)
  database/schema.sql      SQLite-Schema (Beträge als Integer-Cent)
  modules/
    money.py  dates.py     Cent-Arithmetik + deutsche Formate/Parser
    config.py  logging_setup.py  seed.py  budget.py  history.py
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
