"""Locate bundled resource files in both source and frozen (PyInstaller) runs."""

import os
import sys

# PyInstaller unpacks bundled data next to the executable (one-dir mode)
# and exposes the location as sys._MEIPASS; source runs use the repo root.
if getattr(sys, "frozen", False):
    BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(*parts: str) -> str:
    """Absolute path to a bundled resource, e.g. resource_path('assets', 'x.png')."""
    return os.path.join(BASE_DIR, *parts)
