# -*- coding: utf-8 -*-
"""Decoder regression tests.

All samples are public reference frames (mode-s.org / dump1090 docs), so these
assertions check the code against an external standard rather than against
itself.
"""

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sdr.modes import bits_to_hex, checksum, cpr_global, decode_msg


def h2b(h):
    bits = []
    for ch in h:
        v = int(ch, 16)
        bits += [(v >> 3) & 1, (v >> 2) & 1, (v >> 1) & 1, v & 1]
    return bits


# ---------------------------------------------------------------- samples
KLM_ID = "8D4840D6202CC371C32CE0576098"  # callsign KLM1023
ALT_38K = "8D40621D58C382D690C8AC2863A7"  # 38000 ft, even frame
ALT_38K_ODD = "8D40621D58C386435CC412692AD6"  # matching odd frame
VEL_159 = "8D485020994409940838175B284F"  # 159 kt / 182.9 deg / -832 fpm


def test_crc():
    for h in (KLM_ID, ALT_38K, ALT_38K_ODD, VEL_159):
        assert checksum(h2b(h)) == 0, h


def test_callsign():
    d = decode_msg(h2b(KLM_ID))
    assert d["icao"] == "4840D6"
    assert d["callsign"] == "KLM1023"


def test_altitude():
    assert decode_msg(h2b(ALT_38K))["alt"] == 38000


def test_velocity():
    d = decode_msg(h2b(VEL_159))
    assert abs(d["gs"] - 159.2) < 0.5
    assert abs(d["trk"] - 182.9) < 0.5
    assert d["vs"] == -832


def test_cpr():
    ev = decode_msg(h2b(ALT_38K))
    od = decode_msg(h2b(ALT_38K_ODD))
    ev["t"] = time.time() + 1
    od["t"] = time.time()
    lat, lon = cpr_global(
        {"lat": ev["cpr"][0], "lon": ev["cpr"][1], "t": ev["t"]},
        {"lat": od["cpr"][0], "lon": od["cpr"][1], "t": od["t"]},
    )
    assert abs(lat - 52.25720) < 1e-4
    assert abs(lon - 3.91937) < 1e-4


def test_cpr_rejects_stale_pair():
    ev = {"lat": 93000, "lon": 51372, "t": 0.0}
    od = {"lat": 74158, "lon": 50194, "t": 100.0}
    assert cpr_global(ev, od) is None


def test_hex():
    assert bits_to_hex(h2b(KLM_ID)) == KLM_ID


# ---------------------------------------------------------------- physics layer
import numpy as np

from sdr.modes import HALF, PREAMBLE, Store, chunk_pulses, nl, try_decode, update_plane


def synth_tx(hexmsg=KLM_ID):
    """Synthesise a magnitude array that carries one real frame."""
    bits = h2b(hexmsg)
    n = PREAMBLE + 2 * HALF * len(bits) + 64
    m = np.full(n, 0.01)
    for hb in (0, 2, 7, 9):  # the four preamble pulses
        m[hb * HALF : hb * HALF + HALF] = 1.0
    base = PREAMBLE
    for i, b in enumerate(bits):  # PPM: high in first or second half
        s = base + i * 2 * HALF
        if b:
            m[s : s + HALF] = 1.0
        else:
            m[s + HALF : s + 2 * HALF] = 1.0
    return m


def test_nl_branches():
    assert nl(0) == 59
    assert nl(89.0) == 1
    assert nl(-89.0) == 1
    assert nl(52.25) == 36


def test_chunk_pulses_finds_the_preamble():
    m = synth_tx()
    idx = chunk_pulses(m, 0.5)
    assert idx and idx[0] == 0


def test_chunk_pulses_on_short_block():
    assert len(chunk_pulses(np.zeros(8), 0.5)) == 0


def test_try_decode_roundtrip():
    m = synth_tx()
    bits = try_decode(m, 0, 112)
    assert bits is not None
    assert bits_to_hex(bits) == KLM_ID


def test_try_decode_rejects_garbage():
    rng = np.random.RandomState(0)
    m = rng.rand(600) * 0.05 + 0.01
    assert try_decode(m, 0, 112) is None


def test_try_decode_needs_room():
    assert try_decode(np.ones(100), 0, 112) is None


def test_store_accumulates():
    st = Store()
    d = decode_msg(h2b(KLM_ID))
    d["hex"] = KLM_ID
    update_plane(st, d)
    planes, total, rate, status = st.snapshot()
    assert "4840D6" in planes
    assert planes["4840D6"]["callsign"] == "KLM1023"
    assert planes["4840D6"]["n"] == 1
    assert st.planes["4840D6"]["last_hex"] == KLM_ID


def test_update_plane_resolves_position_and_trail():
    st = Store()
    ev = decode_msg(h2b(ALT_38K))
    ev["hex"] = ALT_38K
    od = decode_msg(h2b(ALT_38K_ODD))
    od["hex"] = ALT_38K_ODD
    od["t"] = ev["t"] - 0.5
    update_plane(st, ev)
    update_plane(st, od)
    p = st.snapshot()[0]["40621D"]
    assert abs(p["lat"] - 52.26) < 0.02
    assert abs(p["lon"] - 3.9) < 0.2
    assert len(p["trail"]) == 1


def test_decode_ignores_other_downlink_formats():
    bits = h2b(KLM_ID)
    bits[0:5] = [0, 0, 1, 0, 0]  # DF4 has no ADS-B payload
    d = decode_msg(bits)
    assert d["df"] == 4
    assert "icao" not in d


def test_decode_handles_short_frames():
    d = decode_msg([0, 1, 0, 1, 1] + [0] * 51)
    assert d["n"] == 56
    assert "icao" not in d


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print("  PASS  %s" % name)
        except AssertionError as e:
            failed += 1
            print("  FAIL  %s  %s" % (name, e))
    print("\n%s" % ("all passed" if failed == 0 else "%d failed" % failed))
    sys.exit(1 if failed else 0)
