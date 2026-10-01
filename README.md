# PyKundenkarte Desktop

Lokales Windows-Fenster mit Kundenliste und zoombarer Deutschlandkarte. Die Oberfläche verwendet PySide6, keinen Webserver, keine Online-Kartenkacheln und kein Geocoding. Kundenadressen werden ausschließlich auf dem eigenen Rechner verarbeitet. Marker sind **ungefähre PLZ-Referenzen**, keine Kunden- oder Hauskoordinaten.

## Ohne Administratorrechte starten

Den gesamten Projektordner lokal ablegen oder ein ZIP vollständig entpacken. 64-Bit-Python ab Version 3.10 mit `venv` und `pip` muss vorhanden sein. `data/DE.txt` für Marker bereitlegen; `data/bundeslaender.geojson` liefert die optionalen Bundesländerflächen. `start_windows.bat` doppelklicken: Beim ersten Start richtet `einrichten_windows.bat` die `.venv` **im Projektordner** ein und installiert die Version aus `requirements.txt`. Dafür wird einmalig eine erreichbare Python-Paketquelle benötigt, aber kein Administratorzugang. Spätere Starts laufen offline. `.venv` nicht zwischen Rechnern kopieren. Wenn kein Fenster erscheint, `start_debug_windows.bat` doppelklicken.

Manuelle Befehle im Projektordner (PowerShell):

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Wenn `py -3.14` nicht verfügbar ist, `py -3` oder die vorhandene 64-Bit-Version verwenden. Ohne erreichbare Paketquelle muss die IT die Pakete lokal bereitstellen; das Startskript versucht keine Onlineinstallation, wenn PySide6 bereits in `.venv` vorhanden ist.

## Lokale Ortsdatei

Die öffentliche GeoNames-Datei `DE.txt` gehört als `data/DE.txt` in den Projektordner neben `app.py` und wird beim Start automatisch lokal gelesen. Sie enthält PLZ, Ortsnamen, Bundesländer und geschätzte Koordinaten, keine Kundendaten. [DE.zip herunterladen](https://download.geonames.org/export/zip/DE.zip) und `DE.txt` daraus entpacken. Quelle/Lizenz: GeoNames, www.geonames.org, CC BY 4.0. Bei „Ortsdatei ändern …“ kann während der Sitzung eine andere lokale `DE.txt` oder `DE.zip` gewählt werden.

**Abgleich: PLZ zuerst.** Wenn die PLZ in `DE.txt` existiert, bekommt der Kunde eine grobe PLZ-Position. Gibt es mehrere Zeilen mit derselben PLZ, wird zunächst ein passender Ortsname gesucht (auch eine Variante wie „Eisleben“ / „Lutherstadt Eisleben“). Gibt es keinen Treffer oder ist die Ortszelle leer, wird die **erste gültige Zeile dieser PLZ in Dateireihenfolge** genommen. Die Tabelle kennzeichnet das als „PLZ-Referenz · Ort nicht abgeglichen“. Das Bundesland stammt dann ebenfalls aus dieser gewählten Zeile und kann vom tatsächlichen Kundenort abweichen. Fehlt die PLZ in `DE.txt` oder fehlen notwendige Kundendaten, erscheint der Datensatz unter „Ohne verlässliche Position“. Straßen und Hausnummern werden nie geocodiert.

## Bundesländergrenzen offline anzeigen

Einmalig die [vereinfachte GeoJSON-Datei mit 16 Bundesländern](https://static.geodataviewer.com/datasets/germany-states.geojson) herunterladen und als `data/bundeslaender.geojson` im Projektordner speichern. Sie enthält nur öffentliche Grenzlinien und keine Kundendaten. Beim nächsten Start werden die Bundesländerflächen mit ihren Grenzen als Kartenhintergrund angezeigt. Zum Weitergeben diese Datei zusammen mit `data/DE.txt` kopieren. **Während die Anwendung läuft, wird nichts heruntergeladen.** Wenn die Datei fehlt oder ungültig ist, bleibt die Kartenfläche leer; Kundenmarker und Großstadtnamen werden trotzdem angezeigt. Erwartet wird GeoJSON mit 16 Polygon- oder MultiPolygon-Features in WGS84 (Längengrad, Breitengrad). Quelle: © GeoBasis-DE / BKG, vermittelt durch geoBoundaries und GeoDataViewer; Datenlizenz Deutschland – Namensnennung – Version 2.0, https://www.govdata.de/dl-de/by-2-0. Die Grenzen sind vereinfacht und für die Kartenansicht bestimmt.

## Kunden einlesen und Karte bedienen

Über „CSV öffnen …“ eine Datei lokal auswählen. Im Zuordnungsdialog die Spalten Kundenname, Straße, PLZ und Ort auswählen; Hausnummer und Land sind optional. Die Ortsspalte muss vorhanden sein, **einzelne Ortszellen dürfen leer sein**. Die App benötigt keine Koordinaten in der Kunden-CSV. Sie erkennt Semikolon, Komma, Tabulator und Pipe sowie UTF-8, Windows-1252 und ISO-8859-1. PLZ werden als Text gelesen; `01069` behält die Null. Eine genau vierstellige numerische deutsche PLZ (z. B. `1189`) wird im Speicher zu `01189` ergänzt. Bereits vorhandene CSV-Zeilen bleiben unverändert, neu hinzugefügte Kunden werden mit fünfstelliger PLZ gespeichert. Leeres Land gilt als Deutschland; andere Länder können mit `DE.txt` nicht verortet werden.

Mit „+ Kunde hinzufügen“ oberhalb der Karte einen Eintrag anlegen. Der Dialog fragt Kundenname, Straße, PLZ und Ort ab, aber keine Hausnummer. „In CSV speichern“ ergänzt eine neue Zeile in der **gerade geöffneten** Kunden-CSV; zusätzliche CSV-Spalten, einschließlich Hausnummer, bleiben für diese Zeile leer. Die bisherigen CSV-Zeilen und ihre Kodierung bleiben erhalten. Für diese Funktion ist Schreibzugriff auf die CSV und ihren Ordner nötig. Wird die CSV außerhalb der Anwendung verändert, muss sie erneut geöffnet werden, bevor ein weiterer Eintrag gespeichert werden kann. Zum Weitergeben kann jede Person ihre eigene Kopie der CSV verwenden.

Suche und PLZ-Anfangsfilter wirken zusammen auf Karte und Tabelle. Die Suche umfasst Kundenname, Straße, PLZ, Ort und das **aus dem gewählten PLZ-Eintrag stammende Bundesland**. `Hessen && Baden-Württemberg` im Suchfeld findet eines der beiden Länder; `64 && 57` im PLZ-Feld findet PLZ, die mit **64 oder 57** beginnen. Innerhalb eines Feldes bedeutet `&&` ODER, zwischen den beiden Feldern gilt UND. Großschreibung/Umlaute spielen bei der Suche keine Rolle, auch „Baden-Württenberg“ wird erkannt. Mehrere Wörter ohne `&&` müssen zusammen passen. Trefferzahl und Zahl der Kunden auf der Karte werden angezeigt. Bei leeren Ergebnissen gibt es keine Kundenmarker. Kunden mit identischer Referenzposition teilen sich einen Marker mit Anzahl; ein Klick öffnet die Kundenauswahl und danach die Adresse. „Auf der Karte“ zählt Kunden, nicht einzelne Markersymbole.

Die Karte verwendet bei vorhandener GeoJSON-Datei die Bundesländerflächen und ihre Grenzen; einen zusätzlichen groben Deutschlandumriss gibt es nicht mehr. Sie beschriftet ausschließlich einige Großstädte zur Orientierung. Mit Mausrad oder den Tasten „+“ und „−“ zoomen; mit gedrückter Maustaste verschieben und mit „Übersicht“ zurücksetzen. Beim Zoomen kommen keine weiteren Ortsnamen aus `DE.txt` hinzu. Kundenmarker und Tabelle reagieren gemeinsam auf Suche und PLZ-Filter. Straßen und Hausnummern werden nicht kartiert.

## Dateien und Anpassung

- `app.py`: Desktop-Oberfläche und gemeinsames Aktualisieren von Liste und Karte.
- `kundenkarte/csv_io.py`: CSV-Erkennung, PLZ als Text.
- `kundenkarte/customer_csv.py`: sicheres lokales Anhängen neuer Kunden an die geöffnete CSV.
- `kundenkarte/customers.py`: Spaltenvorschläge, PLZ-Normalisierung, Validierung und Filter.
- `kundenkarte/postcodes.py`: lokaler Import von `DE.txt`/`DE.zip` und PLZ-zuerst-Auswahl in `PostcodeLookup.resolve`.
- `kundenkarte/map_view.py`: zoombare Offline-Karte mit optionalen Bundesländergrenzen, Großstadtnamen und Kundenmarkern.
- `beispiel_kunden.csv`: erfundene Testdaten ohne echte Kunden.
- `data/DE.txt`: von euch lokal bereitgestellte Ortsdatei.
- `data/bundeslaender.geojson`: optional lokal bereitgestellte Bundesländergrenzen.

Andere CSV-Überschriften lassen sich direkt im Importdialog zuordnen. Für zusätzliche automatische Vorschläge die Aliaslisten in `kundenkarte/customers.py` unter `FIELDS` ergänzen. Die Positionierungsregel steht in `PostcodeLookup.resolve` in `kundenkarte/postcodes.py`; Symbolfarben und Beschriftungen stehen in `kundenkarte/map_view.py`. Nach Änderungen an Python-Dateien die App neu starten.

Annahmen und Grenzen: Eine vorhandene PLZ wird auch bei widersprüchlichem Ortsnamen als grobe Referenz verwendet. Mehrere Positionen derselben PLZ können auseinanderliegen; die erste Zeile ist eine feste, aber nicht zwingend geografisch optimale Wahl. Die angezeigten Adressen bleiben unverändert aus der Kunden-CSV, ihre Marker sind keine genauen Filialstandorte. Für echte Straßen- und Hauspositionen wäre ein gesonderter, intern zugelassener Offline-Adressbestand nötig.

Zum Weitergeben den vollständigen Projektordner einschließlich der beiden **öffentlichen** `data`-Dateien kopieren. `.venv` nicht mitkopieren; jeder Rechner richtet eine eigene Umgebung ein. Echte Kunden-CSV-Dateien und Protokolle gehören nicht in einen gemeinsam genutzten Quellcode-Ordner oder ein Git-Repository.
