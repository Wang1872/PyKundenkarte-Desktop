"""Lokale PLZ-Ortszuordnung; niemals Netzwerkzugriffe oder Kundenadressen senden."""

import csv
from collections import defaultdict
from io import BytesIO, StringIO
from math import isfinite
import re
from zipfile import BadZipFile, ZipFile

from .csv_io import CSVError


def _name(text: str) -> str:
    return " ".join(text.casefold().split())


def _place_words(text: str) -> tuple[str, ...]:
    """Offizielle Ortszusätze und Schreibweisen für einen vorsichtigen Abgleich."""
    text = _name(text)
    for source, target in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(source, target)
    titles = {"lutherstadt", "hansestadt", "landeshauptstadt", "kreisstadt",
              "universitaetsstadt", "stadt", "gemeinde"}
    articles = {"am", "an", "der", "in", "im", "bei", "die", "das", "den"}
    return tuple(word for word in re.findall(r"[a-z0-9]+", text)
                 if word not in titles and word not in articles)


def _number(text: str, lower: float, upper: float):
    try:
        value = float(text.strip().replace(",", "."))
    except ValueError:
        return None
    return value if isfinite(value) and lower <= value <= upper else None


class PostcodeLookup(dict):
    """Lokale PLZ-Referenzen in der Reihenfolge der GeoNames-Datei."""

    def __init__(self, *args, by_city=None, state_by_city=None, entries=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.by_city = by_city or {}
        self.state_by_city = state_by_city or {}
        self.entries = entries or {}

    def resolve(self, postcode: str, city: str):
        """Ort bevorzugen; sonst ersten Datensatz der vorhandenen PLZ verwenden.

        Rückgabe: (Koordinaten, Bundesland, Referenzort, Art des Abgleichs).
        Keine Schätzung anhand einer anderen PLZ oder einer Kundenstraße.
        """
        options = self.entries.get(postcode, ())
        if not options:
            return None
        exact = _name(city)
        for place, point, state in options:
            if exact and place == exact:
                return point, state, place, "ort"

        sought = _place_words(city)
        if sought and any(len(word) >= 4 for word in sought):
            sought_set = set(sought)
            for place, point, state in options:
                words = _place_words(place)
                if (words and words[0] == sought[0]
                        and (sought_set <= set(words) or set(words) <= sought_set)):
                    return point, state, place, "namensvariante"

        place, point, state = options[0]
        return point, state, place, "plz"

    def position_for(self, postcode: str, city: str):
        """Position zu einer PLZ, bevorzugt anhand des angegebenen Orts."""
        match = self.resolve(postcode, city)
        return match[0] if match else None

    def state_for(self, postcode: str, city: str) -> str:
        """Bundesland des gewählten lokalen PLZ-Referenzdatensatzes."""
        match = self.resolve(postcode, city)
        return match[1] if match else ""


def _geonames_text(raw: bytes) -> str:
    if raw.startswith(b"PK\x03\x04"):
        try:
            with ZipFile(BytesIO(raw)) as archive:
                matches = [info for info in archive.infolist()
                           if info.filename.rsplit("/", 1)[-1].upper() == "DE.TXT"]
                if len(matches) != 1 or matches[0].file_size > 15_000_000:
                    raise CSVError("Das ZIP braucht genau eine GeoNames-Datei DE.txt (höchstens 15 MB).")
                raw = archive.read(matches[0])
        except (BadZipFile, RuntimeError, OSError) as exc:
            raise CSVError("Die lokale GeoNames-ZIP-Datei konnte nicht gelesen werden.") from exc
    try:
        return raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise CSVError("Die GeoNames-Datei muss UTF-8-kodiert sein.") from exc


def _load_geonames(text: str):
    """Gültige Datensätze ohne Umordnung und ohne Verlust von Mehrfach-PLZ lesen."""
    entries = defaultdict(list)  # PLZ -> [(Ortsname, (Breite, Länge), Bundesland), ...]
    invalid = 0
    for row in csv.reader(StringIO(text), delimiter="\t"):
        if len(row) != 12:
            invalid += 1
            continue
        country, postcode, place, state, *_rest = row
        lat = _number(row[9], -90, 90)
        lon = _number(row[10], -180, 180)
        postcode = postcode.strip()
        place = _name(place)
        if country != "DE" or len(postcode) != 5 or not postcode.isascii() or not postcode.isdigit() or not place or lat is None or lon is None:
            invalid += 1
            continue
        entries[postcode].append((place, (lat, lon), state.strip()))

    if not entries:
        raise CSVError("Keine gültigen deutschen PLZ in der lokalen GeoNames-Datei gefunden.")

    by_city = {}
    state_by_city = {}
    flat = {}
    ambiguous = 0
    for postcode, options in entries.items():
        by_city[postcode] = {}
        state_by_city[postcode] = {}
        for place, point, state in options:
            by_city[postcode].setdefault(place, point)
            state_by_city[postcode].setdefault(place, state)
        flat[postcode] = options[0][1]
        if len(by_city[postcode]) > 1:
            ambiguous += 1
    return PostcodeLookup(flat, by_city=by_city, state_by_city=state_by_city,
                          entries=dict(entries)), invalid, ambiguous


def load_postcodes(raw: bytes):
    """Verarbeitet ausschließlich die lokal bereitgestellte GeoNames-DE-Datei."""
    if raw.startswith(b"PK\x03\x04"):
        return _load_geonames(_geonames_text(raw))
    if raw.lstrip(b"\xef\xbb\xbf \r\n").startswith(b"DE\t"):
        return _load_geonames(_geonames_text(raw))
    raise CSVError("Bitte die GeoNames-Datei DE.txt oder DE.zip für Deutschland auswählen.")
