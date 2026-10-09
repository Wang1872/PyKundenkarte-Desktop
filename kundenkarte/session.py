"""Lokale Sitzungsdaten ohne Klartext-Kundenadressen speichern."""

import hashlib
import json
import os
from pathlib import Path
import tempfile


COLORS = {
    "Blau": "#2563eb",
    "Koralle": "#e2685b",
    "Salbei": "#3f9874",
}


def customer_key(customer: dict) -> str:
    """Stabiler Schlüssel statt einer von der CSV-Reihenfolge abhängigen Zeilennummer."""
    fields = ("name", "street", "number", "postcode", "city", "country")
    identity = "\x1f".join(str(customer.get(field, "")).strip().casefold() for field in fields)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


class SessionStore:
    """Pro Windows-Benutzer unter LOCALAPPDATA, getrennt von der EXE und CSV."""

    def __init__(self, path: Path | None = None):
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
        self.path = path or base / "PyKundenkarte" / "session.json"
        self.data = {"last_csv": "", "files": {}}
        try:
            if self.path.stat().st_size <= 25_000_000:
                saved = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(saved, dict) and isinstance(saved.get("files"), dict):
                    self.data = saved
        except (OSError, ValueError, UnicodeError):
            pass

    @staticmethod
    def _key(path: str) -> str:
        return hashlib.sha256(str(Path(path).resolve()).casefold().encode("utf-8")).hexdigest()

    def last_csv(self) -> str:
        value = self.data.get("last_csv", "")
        return value if isinstance(value, str) else ""

    def for_file(self, path: str) -> dict:
        state = self.data.get("files", {}).get(self._key(path), {})
        return state.copy() if isinstance(state, dict) else {}

    def save_file(self, path: str, state: dict) -> bool:
        """Mit atomarem Austausch speichern; Fehler nie mit Pfaden ausgeben."""
        self.data["last_csv"] = str(Path(path).resolve())
        self.data.setdefault("files", {})[self._key(path)] = state
        temp = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp = tempfile.mkstemp(prefix=".session-", suffix=".tmp", dir=self.path.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(self.data, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.path)
            return True
        except (OSError, TypeError, ValueError):
            return False
        finally:
            if temp is not None:
                try:
                    os.unlink(temp)
                except OSError:
                    pass
