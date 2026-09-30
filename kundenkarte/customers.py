"""Kunden validieren, nur über lokale PLZ-/Ortsdaten verorten und filtern."""


FIELDS = {
    "name": ("Kundenname", True, ("kundenname", "kunde", "name", "firma", "customer")),
    "street": ("Straße", True, ("straße", "strasse", "street", "anschrift")),
    "number": ("Hausnummer", False, ("hausnummer", "hausnr", "hausnr.", "nummer")),
    "postcode": ("Postleitzahl", True, ("postleitzahl", "plz", "zip", "postal code")),
    "city": ("Ort", True, ("ort", "stadt", "city")),
    "country": ("Land", False, ("land", "country")),
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


def prepare(rows: list[dict], mapping: dict[str, str]) -> list[dict]:
    result = []
    for row_no, source in enumerate(rows, start=2):
        item = {field: source[column].strip() if column != "—" else "" for field, column in mapping.items()}
        item["postcode"] = normalize_postcode(item["postcode"], item["country"])
        item["row"] = row_no
        item["lat"] = None  # Interne Kartenposition; nie aus der Kunden-CSV.
        item["lon"] = None
        item["state"] = ""
        item["precision"] = ""
        missing = [FIELDS[field][0] for field in ("name", "street", "postcode", "city") if not item[field]]
        item["issue"] = "Fehlt: " + ", ".join(missing) if missing else ""
        result.append(item)
    return result


def locate(customers: list[dict], postcodes) -> list[dict]:
    """Ordnet nur eindeutig passende PLZ-/Ortsnamen einer lokalen Referenz zu."""
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
            point = postcodes.position_for(item["postcode"], item["city"])
            if point is None:
                item["issue"] = ("PLZ fehlt in der lokalen Ortsdatei" if
                                 item["postcode"] not in postcodes.by_city else
                                 "PLZ und Ort passen nicht eindeutig zusammen")
            else:
                item["lat"], item["lon"] = point
                item["state"] = postcodes.state_for(item["postcode"], item["city"])
                item["precision"] = "Ort/PLZ"
        result.append(item)
    return result


def _search_text(value: str) -> str:
    """Großschreibung/Umlaute sowie die häufige Schreibweise Württenberg angleichen."""
    value = value.casefold().replace("württenberg", "württemberg")
    value = value.replace("wuerttenberg", "wuerttemberg")
    for source, target in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"), ("-", " ")):
        value = value.replace(source, target)
    return value


def filter_customers(customers: list[dict], query: str, prefix: str) -> list[dict]:
    """&& ist ODER innerhalb eines Feldes; beide Felder zusammen sind UND."""
    alternatives = [_search_text(part).split() for part in query.split("&&") if part.strip()]
    prefixes = [part.strip() for part in prefix.split("&&") if part.strip()]
    result = []
    for item in customers:
        if prefixes and not any(item["postcode"].startswith(part) for part in prefixes):
            continue
        searchable = _search_text(" ".join(item[field] for field in
                                    ("name", "street", "postcode", "city", "state")))
        if alternatives and not any(all(term in searchable for term in terms)
                                    for terms in alternatives):
            continue
        result.append(item)
    return result
