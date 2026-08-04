# Änderungen

Alle nennenswerten Änderungen an diesem Programm, neueste zuerst.
Versionierung nach [SemVer](https://semver.org/lang/de/).

## [3.8.0] – 2026-08-04

Der erste Teil des großen Umbaus: neues Erscheinungsbild, ein deutlich
schnellerer Start und fünf behobene Rechenfehler.

### Behoben

- **Diagramme zeigten falsche Beträge.** Die Beschriftung der senkrechten Achse
  war um den Faktor 100 zu niedrig – wo 3.500 € standen, stand „35 €“. Betroffen
  waren Verlauf und Prognose.
- **„Ausgaben nach Kategorie“ zeigte nur einen Teil des Monats.** Fixkosten wie
  Miete, Strom und Versicherungen fehlten in der Aufschlüsselung komplett,
  obwohl sie meist der größere Teil der Ausgaben sind. Sie werden jetzt überall
  mitgezählt – im Dashboard, im Verlauf, in der Jahresübersicht und im
  PDF-Bericht. Sparraten bekommen dabei einen eigenen Posten, denn verschobenes
  Geld ist keine Ausgabe.
- **„Letzten Import rückgängig machen“ ließ Buchungen stehen.** Bei zwei
  identischen Buchungen am selben Tag wurde nur eine davon entfernt.
- **Die Suche fand ältere Buchungen nicht.** Gesucht wurde nur in den 5.000
  neuesten Einträgen; alles davor galt als „nicht gefunden“. Jetzt wird der
  ganze Bestand durchsucht – zusätzlich nach Kategorie und nach Betrag, sodass
  die Eingabe „42,85“ die passende Buchung findet.
- **„Alle Daten löschen“ konnte sich selbst rückgängig machen.** Beim nächsten
  Start wurden die Startdaten erneut eingelesen.
- **Texte in Import/Export brachen mitten im Satz ab** und wurden teilweise von
  den Schaltflächen überdeckt.
- **Angehakte Kontrollkästchen waren ein blaues Quadrat ohne Haken.**
- **In der Navigation sahen immer zwei Einträge gleichzeitig aktiv aus.**

### Neu und geändert

- **Neues Erscheinungsbild.** Ruhige, papierartige Flächen, eine einzige
  Akzentfarbe und klare Haarlinien statt Kästen im Kasten. Heller und dunkler
  Modus sind eigenständig gestaltet, nicht nur umgefärbt. Die fast schwarze
  Seitenleiste im hellen Modus ist verschwunden.
- **Beträge stehen jetzt sauber untereinander**, weil alle Ziffern gleich breit
  gesetzt werden.
- **Das Dashboard ist neu aufgebaut.** Zwei Spalten statt einer langen Liste,
  jede Kennzahl mit ihrem Verlauf über zwölf Monate, ein Vergleich von Einnahmen
  und Ausgaben je Monat und eine sortierte Kategorie-Rangliste mit
  Budget-Markierung anstelle des unübersichtlichen Ringdiagramms.
- **Ausgabe erfassen geht direkt vom Dashboard** – per Schaltfläche oder Strg+N.
  Vorher waren dafür drei Klicks über zwei andere Ansichten nötig.
- **Alle Diagramme sind neu gezeichnet** und übernehmen Farben und Schrift der
  App.

### Schneller

- Der Start dauert nur noch etwa halb so lange. Ansichten entstehen erst beim
  Öffnen, und die Bausteine für Berichte werden erst geladen, wenn wirklich ein
  Bericht erzeugt wird.
- Die Verlaufsansicht baut sich rund viermal schneller auf.

### Sonstiges

- Das Programm steht ausdrücklich unter der **GPL v3**; der Lizenztext liegt
  jetzt als `LICENSE` bei.

---

Ältere Versionen sind in den
[GitHub-Releases](https://github.com/huliguli/HaushaltsManager/releases)
dokumentiert.
