"""Lokale PLZ-Ortszuordnung; niemals Netzwerkzugriffe oder Kundenadressen senden."""

import csv
from collections import defaultdict
from io import BytesIO, StringIO
from math import isfinite
import re
from statistics import median
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
              "universitaetsstadt", "stadt", "gemeinde", "ort", "stadtteil", "stadtbezirk", "stadtgemeinde", "stadtverband", "Flughafen"}
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
    """Bisheriger PLZ-Zugriff plus eindeutige Zuordnung nach PLZ und Ort."""

    def __init__(self, *args, by_city=None, state_by_city=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.by_city = by_city or {}
        self.state_by_city = state_by_city or {}

    def resolve(self, postcode: str, city: str):
        """Gibt (Position, Bundesland, Ortsname) nur bei eindeutigem PLZ-Abgleich zurück."""
        places = self.by_city.get(postcode, {})
        exact = _name(city)
        if exact in places:
            point = places[exact]
            return (point, self.state_by_city.get(postcode, {}).get(exact, ""), exact) if point else None

        sought = _place_words(city)
        if not sought or not any(len(word) >= 4 for word in sought):
            return None
        sought_set = set(sought)
        candidates = []
        for place, point in places.items():
            words = _place_words(place)
            if (point is not None and words and words[0] == sought[0]
                    and (sought_set <= set(words) or set(words) <= sought_set)):
                candidates.append(place)
        if len(candidates) != 1:
            return None
        place = candidates[0]
        return places[place], self.state_by_city.get(postcode, {}).get(place, ""), place

    def position_for(self, postcode: str, city: str):
        """Kompatibler Positionszugriff, auch für eindeutige Namensvarianten."""
        match = self.resolve(postcode, city)
        return match[0] if match else None

    def state_for(self, postcode: str, city: str) -> str:
        """Bundesland nur bei eindeutig zugeordneter PLZ und Ortsangabe."""
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
    """GeoNames DE.txt: jede PLZ/Ort-Kombination behält ihren eigenen Referenzpunkt."""
    groups = defaultdict(list)  # (PLZ, Ortsname, Bundesland, Kreis) -> Referenzpunkte
    group_states = defaultdict(set)
    postal_places = defaultdict(lambda: defaultdict(set))
    invalid = 0
    for row in csv.reader(StringIO(text), delimiter="\t"):
        if len(row) != 12:
            invalid += 1
            continue
        country, postcode, place, state, state_id, _county, county_id, *_rest = row
        lat = _number(row[9], -90, 90)
        lon = _number(row[10], -180, 180)
        postcode = postcode.strip()
        place = _name(place)
        if country != "DE" or len(postcode) != 5 or not postcode.isascii() or not postcode.isdigit() or not place or lat is None or lon is None:
            invalid += 1
            continue
        key = (postcode, place, state_id.strip(), county_id.strip())
        groups[key].append((lat, lon))
        if state.strip():
            group_states[key].add(state.strip())
        postal_places[postcode][place].add(key)

    if not postal_places:
        raise CSVError("Keine gültigen deutschen PLZ in der lokalen GeoNames-Datei gefunden.")

    centers = {key: (median(point[0] for point in points),
                     median(point[1] for point in points))
               for key, points in groups.items()}
    by_city = {}
    state_by_city = {}
    flat = {}
    ambiguous = 0
    for postcode, places in postal_places.items():
        by_city[postcode] = {place: centers[next(iter(keys))] if len(keys) == 1 else None
                             for place, keys in places.items()}
        state_by_city[postcode] = {}
        for place, keys in places.items():
            states = group_states[next(iter(keys))] if len(keys) == 1 else set()
            state_by_city[postcode][place] = next(iter(states)) if len(states) == 1 else ""
        positions = [point for point in by_city[postcode].values() if point is not None]
        if len(places) == 1 and len(positions) == 1:
            flat[postcode] = positions[0]
        else:
            ambiguous += 1
    return PostcodeLookup(flat, by_city=by_city, state_by_city=state_by_city), invalid, ambiguous


def load_postcodes(raw: bytes):
    """Verarbeitet ausschließlich die lokal bereitgestellte GeoNames-DE-Datei."""
    if raw.startswith(b"PK\x03\x04"):
        return _load_geonames(_geonames_text(raw))
    if raw.lstrip(b"\xef\xbb\xbf \r\n").startswith(b"DE\t"):
        return _load_geonames(_geonames_text(raw))
    raise CSVError("Bitte die GeoNames-Datei DE.txt oder DE.zip für Deutschland auswählen.")
