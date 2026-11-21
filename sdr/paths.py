# -*- coding: utf-8 -*-
"""Runtime dependency paths.

These directories are **not** committed; ``scripts/setup_windows.py`` and
``pip install`` create them locally:

    libiio/   official libiio binaries (libiio.dll)
    vendor/   pip packages (a venv is preferred, but this keeps things simple)
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LIBIIO = os.path.join(ROOT, "libiio")
VENDOR = os.path.join(ROOT, "vendor")


def setup():
    """Put the libiio DLL directory and vendor packages on the search path."""
    if os.path.isdir(LIBIIO):
        os.environ["PATH"] = LIBIIO + os.pathsep + os.environ.get("PATH", "")
        try:
            os.add_dll_directory(LIBIIO)  # Windows 3.8+
        except (AttributeError, OSError):
            pass
    if os.path.isdir(VENDOR) and VENDOR not in sys.path:
        sys.path.insert(0, VENDOR)


def vendors_ready():
    return os.path.isdir(LIBIIO) and os.path.isdir(VENDOR)
