# -*- coding: utf-8 -*-
"""Tests for the datum and projection helpers.

There is no published closed form for GCJ-02, so we assert the properties that
must hold: round-trip accuracy, plausible offset size, and pass-through outside
mainland China.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sdr import geo

BEIJING = (40.0689, 116.3072)


def test_roundtrip():
    lat, lon = geo.wgs2gcj(*BEIJING)
    back = geo.gcj2wgs(lat, lon)
    assert abs(back[0] - BEIJING[0]) < 1e-6
    assert abs(back[1] - BEIJING[1]) < 1e-6


def test_offset_magnitude():
    """The GCJ-02 shift around Beijing is 300-800 m; anything else means a bug."""
    lat, lon = geo.wgs2gcj(*BEIJING)
    d, _ = geo.distance_bearing(BEIJING[0], BEIJING[1], lat, lon)
    assert 0.3 < d < 0.8, "offset %.0f m" % (d * 1000)


def test_outside_china_untouched():
    for pt in (
        (35.6762, 139.6503),  # Tokyo
        (51.5072, -0.1276),  # London
        (-33.8688, 151.2093),
    ):  # Sydney
        assert geo.wgs2gcj(*pt) == pt
        assert geo.gcj2wgs(*pt) == pt


def test_distance_bearing():
    # Beijing to Tianjin: ~110-135 km, east-southeast.
    d, b = geo.distance_bearing(40.0689, 116.3072, 39.13, 117.20)
    assert 110 < d < 135
    assert 130 < b < 160


def test_merc_roundtrip():
    for z in (5, 9, 13):
        x, y = geo.merc(*BEIJING, z)
        lat, lon = geo.inv_merc(x, y, z)
        assert abs(lat - BEIJING[0]) < 1e-4
        assert abs(lon - BEIJING[1]) < 1e-4
