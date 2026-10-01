"""Kunden validieren, nur über lokale PLZ-/Ortsdaten verorten und filtern."""

import re


POSTCODE_RANGE = re.compile(r"([0-9]{1,5})\s*--\s*([0-9]{1,5})")


FIELDS = {
    "name": ("Kundenname", True, ("kundenname", "kunde", "name", "firma", "customer")),
    "street": ("Straße", True, ("straße", "strasse", "street", "anschrift")),
    "number": ("Hausnummer", False, ("hausnummer", "hausnr", "hausnr.", "nummer")),
    "postcode": ("Postleitzahl", True, ("postleitzahl", "plz", "zip", "postal code")),
    "city": ("Ort", True, ("ort", "stadt", "city")),
    "country": ("Land", False, ("land", "country")),
    "email": ("E-Mail", False, ("e-mail", "email", "e-mail-adresse", "emailadresse", "mail")),
    "phone": ("Telefon", False, ("telefon", "telefonnummer", "tel", "tel.", "phone", "mobil", "handy")),
}


def normalize_postcode(postcode: str, country: str = "") -> str:
    """Ergänzt bei deutschen vierstelligen PLZ die verlorene führende Null."""
    postcode = postcode.strip()
    if (country.strip().casefold() in ("", "de", "deutschland", "germany")
            and len(postcode) == 4 and postcode.isascii() and postcode.isdigit()):
        return "0" + postcode
    return postcode


def suggest(field: str, header: list[str]) -> str:
    return next((name for name in header if name.strip().casefold() in FIELDS[field][2]), "—")


def address(item: dict) -> str:
    return ", ".join(part for part in (
        " ".join(p for p in (item["street"], item["number"]) if p),
        " ".join(p for p in (item["postcode"], item["city"]) if p),
        item["country"],
    ) if part)


def contact_lines(item: dict) -> list[str]:
    """Nur vorhandene Kontaktdaten für Marker-Details aufbereiten."""
    return ([f"E-Mail: {item['email']}"] if item.get("email") else []) + (
        [f"Telefon: {item['phone']}"] if item.get("phone") else [])


def prepare(rows: list[dict], mapping: dict[str, str]) -> list[dict]:
    result = []
    for row_no, source in enumerate(rows, start=2):
        item = {field: source[mapping[field]].strip() if mapping.get(field, "—") != "—" else ""
                for field in FIELDS}
        item["postcode"] = normalize_postcode(item["postcode"], item["country"])
        item["row"] = row_no
        item["lat"] = None  # Interne Kartenposition; nie aus der Kunden-CSV.
        item["lon"] = None
        item["state"] = ""
        item["precision"] = ""
        # Für die grobe PLZ-Position darf der Ortswert leer sein; die Spalte bleibt zuordenbar.
        missing = [FIELDS[field][0] for field in ("name", "street", "postcode") if not item[field]]
        item["issue"] = "Fehlt: " + ", ".join(missing) if missing else ""
        result.append(item)
    return result


def locate(customers: list[dict], postcodes) -> list[dict]:
    """Verortet deutsche Kunden nach PLZ; Ortsnamen verfeinern die Auswahl."""
    result = []
    for original in customers:
        item = original.copy()
        if item["issue"]:
            pass
        elif item["country"].casefold() not in ("", "de", "deutschland", "germany"):
            item["issue"] = "Für dieses Land ist keine lokale Ortszuordnung vorhanden"
        elif not getattr(postcodes, "by_city", None):
            item["issue"] = "Lokale Ortsdatei fehlt oder enthält keine passenden Daten"
        else:
            match = postcodes.resolve(item["postcode"], item["city"])
            if match is None:
                item["issue"] = "PLZ fehlt in der lokalen Ortsdatei"
            else:
                point, state, _matched_place, method = match
                item["lat"], item["lon"] = point
                item["state"] = state
                item["precision"] = {
                    "ort": "PLZ-Referenz",
                    "namensvariante": "PLZ-Referenz · Namensvariante",
                    "plz": "PLZ-Referenz · Ort nicht abgeglichen",
                }[method]
        result.append(item)
    return result


def _search_text(value: str) -> str:
    """Großschreibung/Umlaute sowie die häufige Schreibweise Württenberg angleichen."""
    value = value.casefold().replace("württenberg", "württemberg")
    value = value.replace("wuerttenberg", "wuerttemberg")
    for source, target in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"), ("-", " ")):
        value = value.replace(source, target)
    return value


def _matches_postcode(postcode: str, expression: str) -> bool:
    """Präfix oder inklusiven Bereich gleich langer PLZ-Anfänge prüfen."""
    match = POSTCODE_RANGE.fullmatch(expression)
    if match:
        first, last = match.groups()
        return (len(first) == len(last) and len(postcode) >= len(first)
                and first <= postcode[:len(first)] <= last)
    if "--" in expression:
        return False
    return postcode.startswith(expression)


def filter_customers(customers: list[dict], query: str, prefix: str) -> list[dict]:
    """PLZ-Präfixe/Bereiche und Suche kombinieren; && bedeutet jeweils ODER."""
    alternatives = [_search_text(part).split() for part in query.split("&&") if part.strip()]
    postcode_expressions = [part.strip() for part in prefix.split("&&") if part.strip()]
    result = []
    for item in customers:
        if postcode_expressions and not any(_matches_postcode(item["postcode"], part)
                                            for part in postcode_expressions):
            continue
        searchable = _search_text(" ".join(item[field] for field in
                                    ("name", "street", "postcode", "city", "state")))
        if alternatives and not any(all(term in searchable for term in terms)
                                    for terms in alternatives):
            continue
        result.append(item)
    return result
