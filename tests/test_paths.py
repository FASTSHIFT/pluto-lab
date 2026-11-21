# -*- coding: utf-8 -*-
"""Tests for the dependency path helper.

The real directories (libiio/, vendor/) only exist on a configured machine, so
the tests swap in temporary directories and restore the module state afterwards.
"""

import os
import sys
import tempfile

from sdr import paths


def _swap(lib, ven):
    old = (paths.LIBIIO, paths.VENDOR)
    paths.LIBIIO, paths.VENDOR = lib, ven
    return old


def test_setup_without_dirs_is_a_noop():
    missing = os.path.join(tempfile.gettempdir(), "pluto-lab-missing")
    old = _swap(os.path.join(missing, "libiio"), os.path.join(missing, "vendor"))
    try:
        paths.setup()  # must not raise
        assert not paths.vendors_ready()
    finally:
        paths.LIBIIO, paths.VENDOR = old


def test_setup_registers_vendor_and_libiio():
    with tempfile.TemporaryDirectory() as d:
        lib = os.path.join(d, "libiio")
        ven = os.path.join(d, "vendor")
        os.makedirs(lib)
        os.makedirs(ven)
        old = _swap(lib, ven)
        old_path = os.environ.get("PATH", "")
        try:
            paths.setup()
            assert ven in sys.path
            assert paths.vendors_ready()
            assert lib in os.environ["PATH"]

            paths.setup()  # idempotent: no duplicate entry
            assert sys.path.count(ven) == 1
        finally:
            paths.LIBIIO, paths.VENDOR = old
            os.environ["PATH"] = old_path
            while ven in sys.path:
                sys.path.remove(ven)
