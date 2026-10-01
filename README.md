# PyKundenkarte

Lokale Windows-App für Kunden aus einer CSV. Kundenadressen bleiben auf dem Rechner; die App benötigt während der Nutzung kein Internet. Kartenmarker zeigen **ungefähre PLZ-Positionen**, keine genauen Adressen.

## Start aus dem Projektordner

1. Den vollständigen Projektordner entpacken. Die öffentliche Ortsdatei muss unter `data\DE.txt` liegen ([GeoNames DE.zip](https://download.geonames.org/export/zip/DE.zip) herunterladen und `DE.txt` entpacken).
2. `start_windows.bat` doppelklicken. Vorhandenes Python wird genutzt; wenn Python fehlt und Scoop installiert ist, richtet das Skript Python und danach `.venv` selbst ein. Falls Scoop fehlt: [Scoop einrichten](https://scoop.sh/) und erneut starten. **Beim ersten Einrichten** ist Zugang zu Python- und Paketquellen nötig, später nicht mehr. Keine Administratorrechte erforderlich.
3. Falls kein Fenster erscheint, `start_debug_windows.bat` starten.

## Kunden anzeigen

- „CSV öffnen …“ wählen und die Spalten **Kundenname, Straße, PLZ und Ort** zuordnen. Hausnummer, Land, E-Mail und Telefon sind optional. PLZ und Telefonnummern bleiben Text, auch mit führenden Nullen.
- Suche und PLZ-Filter aktualisieren Karte und Tabelle gemeinsam. Beispiele für den PLZ-Filter: `64`, `64 && 57`, `01 -- 09` oder `60 -- 69`. `&&` bedeutet ODER, `--` einen Bereich einschließlich der Grenzen.
- Ein Klick auf einen Marker zeigt die Kundendetails; bei mehreren Kunden am selben Punkt zuerst die Auswahl. „+ Kunde hinzufügen“ speichert einen neuen Eintrag in der geöffneten CSV.

Die App verwendet die PLZ aus der CSV. Gibt es mehrere passende Einträge in `DE.txt`, bevorzugt sie den Ortsnamen; sonst nimmt sie den ersten Eintrag dieser PLZ. Fehlende Positionen erscheinen separat. Es findet **kein Online-Geocoding** statt.

## Fertiges Paket ohne Python

Auf einem Windows-Rechner mit Python `paket_erstellen_windows.bat` starten. Den **ganzen Ordner** `release\PyKundenkarte` weitergeben; die Kollegen starten darin `PyKundenkarte.exe` per Doppelklick. Echte Kunden-CSV-Dateien nicht beilegen.

Optional können Bundesländergrenzen als `data\bundeslaender.geojson` hinzugefügt werden ([Datei](https://static.geodataviewer.com/datasets/germany-states.geojson)). Öffentliche Daten: GeoNames (CC BY 4.0); Bundesländergrenzen: © GeoBasis-DE/BKG, vermittelt durch geoBoundaries/GeoDataViewer, [Datenlizenz Deutschland – Namensnennung – Version 2.0](https://www.govdata.de/dl-de/by-2-0).
