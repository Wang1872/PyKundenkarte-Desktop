"""Pfad zu öffentlichen Kartendaten im Quellcode und im Windows-Paket."""

import sys
from pathlib import Path


def project_dir() -> Path:
    """Im fertigen Paket liegen data-Dateien neben der EXE."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent
