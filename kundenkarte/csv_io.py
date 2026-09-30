"""CSV-Einlesen ohne Netzwerk und ohne numerische Konvertierung von PLZ."""

import csv
import io


class CSVError(ValueError):
    """Meldung ohne Kundendaten oder Originalinhalt der CSV."""


ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "iso-8859-1")
DELIMITERS = (";", ",", "\t", "|")


def read_csv(raw: bytes, encoding: str = "Automatisch", delimiter: str = "Automatisch"):
    if not raw:
        raise CSVError("Die Datei ist leer.")
    choices = ENCODINGS if encoding == "Automatisch" else (encoding,)
    decoded = None
    chosen_encoding = ""
    for codec in choices:
        try:
            decoded = raw.decode(codec)
            chosen_encoding = codec
            break
        except (UnicodeDecodeError, LookupError):
            pass
    if decoded is None:
        raise CSVError("Die Zeichenkodierung konnte nicht gelesen werden.")
    if "\x00" in decoded:
        raise CSVError("Die Datei scheint keine Text-CSV zu sein.")
    if delimiter == "Automatisch":
        try:
            delimiter = csv.Sniffer().sniff(decoded[:8192], delimiters=";,\t|").delimiter
        except csv.Error:
            first = decoded.splitlines()[0] if decoded.splitlines() else ""
            delimiter = max(DELIMITERS, key=first.count)
            if delimiter not in first:
                raise CSVError("Trennzeichen unklar. Bitte beim Einlesen manuell wählen.")
    if delimiter not in DELIMITERS:
        raise CSVError("Dieses CSV-Trennzeichen wird nicht unterstützt.")
    try:
        reader = csv.reader(io.StringIO(decoded, newline=""), delimiter=delimiter, strict=True)
        original_header = next(reader)
        header = [value.strip().lstrip("\ufeff") for value in original_header]
        if not header or any(not name for name in header) or len(header) != len(set(header)):
            raise CSVError("Die Spaltenüberschriften müssen eindeutig und nicht leer sein.")
        rows = []
        for cells in reader:
            if not any(cell.strip() for cell in cells):
                continue
            if len(cells) != len(header):
                raise CSVError(f"CSV-Zeile {reader.line_num}: Anzahl der Felder passt nicht zur Kopfzeile.")
            rows.append(dict(zip(header, cells)))
    except StopIteration:
        raise CSVError("Die Datei enthält keine Kopfzeile.") from None
    except (csv.Error, UnicodeError):
        raise CSVError("CSV-Syntaxfehler. Bitte Kodierung und Trennzeichen prüfen.") from None
    if not rows:
        raise CSVError("Die CSV enthält keine Datensätze.")
    return header, rows, chosen_encoding, delimiter
