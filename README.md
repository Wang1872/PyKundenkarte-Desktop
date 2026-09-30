# PyKundenkarte Desktop

Eine lokale Windows-Anwendung für die Auswertung einer Kunden-CSV. Sie nutzt PySide6-Widgets und die Python-Standardbibliothek, startet ohne Webserver und stellt keinerlei Netzwerkverbindung für Kartendaten oder Geocoding her. Der Python-Code verwendet kein `requests`, kein `urllib`, keine WebEngine und keine externen Karten-, JavaScript- oder Schriftressourcen.

## Installation und Start ohne Administratorrechte

ZIP vollständig in einen beschreibbaren lokalen Ordner entpacken. Python 3.10 oder neuer in 64 Bit ist erforderlich; geprüft wurde die Paketverfügbarkeit für die vom Auftraggeber verwendete Version 3.14.7. `start_windows.bat` doppelklicken. Beim ersten Start wird eine lokale `.venv` eingerichtet und `PySide6-Essentials` dort installiert. Nur **diese Paketinstallation** benötigt einmalig Zugriff auf PyPI oder eine interne Paketquelle. Später startet dieselbe Batch-Datei per `pythonw.exe` das normale Desktop-Fenster ohne Konsole und ohne Internet. Keine Adminrechte, keine PowerShell-Ausführungsrichtlinie.

Manuelle Befehle im entpackten Projektordner (PowerShell):

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Wenn Python 3.14 nicht über `py` erreichbar ist, einen installierten 64-Bit-Python-Interpreter ab 3.10 verwenden. Den Ordner `.venv` nicht zwischen PCs kopieren; jede Person richtet ihn einmalig ein. Ist die Python-Paketquelle gesperrt, muss die IT die Abhängigkeiten bereitstellen oder eine auf Windows gebaute portable App verteilen. Die ZIP enthält keine Windows-EXE. Bei Startproblemen `start_debug_windows.bat` ausführen.

## Daten und Karte

In „Kunden-CSV öffnen“ eine Datei auf dem eigenen PC auswählen. CSV-Spalten für Kundenname, Straße, Hausnummer, PLZ und Ort sind Pflicht; Land und ein Breitengrad-/Längengrad-Paar sind optional. Spaltennamen lassen sich in einem Dialog zuordnen. Semikolon, Komma, Tabulator und Pipe sowie UTF-8, Windows-1252 und ISO-8859-1 werden verarbeitet. PLZ bleibt Text: `01069` bleibt `01069`. Die Suche und der PLZ-Präfixfilter wirken zusammen auf Karte und beide Tabellen. Die Ansicht zeigt Treffer, Marker und Kunden ohne Position separat.

Die Karte ist eine **schematische Koordinatenübersicht ohne Straßen und ohne genaue Verwaltungsgrenzen**. Mausrad zoomt, Ziehen verschiebt sie, Klick auf Marker zeigt Name, Adresse und Genauigkeit. Orange Marker stammen aus der lokalen PLZ-Tabelle und sind **ungefähr**, blau steht für vom CSV bereitgestellte Koordinaten (die App prüft nur den gültigen Zahlenbereich, nicht die Übereinstimmung mit der Adresse). Identische Koordinaten werden zur Auswahl optisch leicht versetzt. Alle unvollständigen, ungültigen oder in der PLZ-Tabelle fehlenden Einträge stehen mit Grund im Reiter „Ohne verlässliche Position“. Beim Filtern bleiben Karte und Tabelle synchron.

Die beigefügte `data/plz_beispiel.csv` enthält **nur vier Demo-PLZ** für die erfundenen Beispieldatensätze; deren Werte sind ungefähre Stadtpositionen, keine echten PLZ-Gebietsmitten. Für tatsächliche Kunden braucht ihr eine von eurer IT geprüfte, lokal vorliegende PLZ-Koordinatentabelle. Das Format ist:

```csv
PLZ;Breitengrad;Längengrad
01069;51.040;13.732
10115;52.532;13.384
```

Die PLZ-Datei über „Lokale PLZ-Tabelle öffnen“ laden. Doppelte PLZ mit voneinander abweichenden Koordinaten werden **nicht** verwendet. Die App speichert die ausgewählte Kunden-CSV oder PLZ-Datei nicht dauerhaft; die Daten verbleiben während der Nutzung im Arbeitsspeicher. Es werden keine Adressen protokolliert. Die Verarbeitung der Kunden-CSV löst keine Netzwerkanfrage aus.

**Genaue Hausadressen ohne Koordinaten:** Dafür ist ein intern bereitgestellter, ausreichend detaillierter und lizenzierter Offline-Adressdatenbestand mit Straße, Hausnummer, PLZ, Ort und Koordinaten nötig (etwa eine lokale SQLite-Tabelle). Diese Version führt bewusst keinen solchen Abgleich und kein externes Geocoding aus. Eine PLZ-Tabelle liefert nur eine Näherung. Wer genaue Marker braucht, muss einen solchen Datensatz intern beschaffen, dessen Aktualität und Mehrdeutigkeiten prüfen und die lokale Zuordnungslogik ergänzen.

## Dateien

- `app.py`: Desktop-Fenster und gemeinsame Filterung.
- `kundenkarte/csv_io.py`: lokales CSV-Einlesen ohne numerische PLZ-Konvertierung.
- `kundenkarte/customers.py`: Zuordnung, Prüfung, Suche und Positionstyp.
- `kundenkarte/postcodes.py`: Import der lokalen PLZ-Positionen.
- `kundenkarte/map_view.py`: zoom- und verschiebbare Qt-Karte ohne Webressourcen.
- `data/plz_beispiel.csv`, `beispiel_kunden.csv`: ausschließlich Demonstration.
- `requirements.txt`, `einrichten_windows.bat`, `start_windows.bat`: Einrichtung und Start.

**Annahmen:** Eine CSV-Zeile ist ein Kundenstandort. Bei leerem Land wird für die PLZ-Zuordnung Deutschland angenommen. Nur vollständige Adressen werden verortet. Positionen aus der CSV haben Vorrang vor PLZ-Positionen. Ein Satz unvollständiger Adressdaten wird in der Hinweisliste geführt, auch wenn er Koordinaten enthält. Es werden keine Kundendaten in diesem Paket mitgeliefert.
