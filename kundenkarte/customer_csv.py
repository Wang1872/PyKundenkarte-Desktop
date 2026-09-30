"""Eine neue Kundenzeile sicher in die gewählte lokale CSV schreiben."""

import csv
import io
import os
from pathlib import Path
import stat
import tempfile

from .csv_io import CSVError, read_csv
from .customers import normalize_postcode


class SaveError(ValueError):
    """Fehlertext ohne Pfad und ohne Kundendaten."""


class CustomerFile:
    def __init__(self, path: str, raw: bytes, headers: list[str],
                 mapping: dict[str, str], encoding: str, delimiter: str):
        self.path = Path(path)
        self.raw = raw
        self.headers = headers
        self.mapping = mapping
        self.encoding = encoding
        self.delimiter = delimiter

    def append(self, fields: dict[str, str]) -> list[dict[str, str]]:
        """Bewahrt vorhandene CSV-Bytes; erkennt zwischenzeitliche Änderungen."""
        missing = [label for field, label in (("name", "Kundenname"), ("street", "Straße"),
                    ("postcode", "PLZ"), ("city", "Ort")) if not fields.get(field, "").strip()]
        if missing:
            raise SaveError("Bitte ausfüllen: " + ", ".join(missing) + ".")
        try:
            current = self.path.read_bytes()
        except OSError:
            raise SaveError("Die CSV-Datei konnte nicht gelesen werden.") from None
        if current != self.raw:
            raise SaveError("Die CSV wurde inzwischen geändert. Bitte erneut öffnen und dann speichern.")

        values = {header: "" for header in self.headers}
        for field in ("name", "street", "postcode", "city"):
            value = fields[field].strip()
            values[self.mapping[field]] = normalize_postcode(value) if field == "postcode" else value
        # Hausnummer und Land bleiben in einer vorhandenen CSV-Spalte leer.
        newline = "\r\n" if b"\r\n" in current else "\n" if b"\n" in current else "\r" if b"\r" in current else "\r\n"
        buffer = io.StringIO(newline="")
        csv.writer(buffer, delimiter=self.delimiter, lineterminator=newline).writerow(
            [values[header] for header in self.headers])
        try:
            encoded = buffer.getvalue().encode("utf-8" if self.encoding == "utf-8-sig" else self.encoding)
        except UnicodeError:
            raise SaveError("Ein Zeichen kann in der CSV-Kodierung nicht gespeichert werden.") from None
        separator = b"" if current.endswith((b"\r", b"\n")) else newline.encode("ascii")
        updated = current + separator + encoded
        try:
            _, rows, _, _ = read_csv(updated, self.encoding, self.delimiter)
        except CSVError:
            raise SaveError("Die ergänzte CSV konnte nicht geprüft werden; es wurde nichts gespeichert.") from None

        temp_path = None
        try:
            mode = stat.S_IMODE(self.path.stat().st_mode)
            fd, temp_path = tempfile.mkstemp(prefix=".pykundenkarte-", suffix=".tmp", dir=self.path.parent)
            with os.fdopen(fd, "wb") as stream:
                stream.write(updated)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temp_path, mode)
            # Bei paralleler Bearbeitung seit dem ersten Lesen nicht ersetzen.
            if self.path.read_bytes() != current:
                raise SaveError("Die CSV wurde inzwischen geändert. Bitte erneut öffnen und dann speichern.")
            os.replace(temp_path, self.path)
            temp_path = None
        except OSError:
            raise SaveError("Speichern fehlgeschlagen. Bitte Schreibrechte und geöffnete CSV prüfen.") from None
        finally:
            if temp_path is not None:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
        self.raw = updated
        return rows
