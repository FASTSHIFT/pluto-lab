# -*- coding: utf-8 -*-
"""Mode S / ADS-B decoding core.

Pure numpy, no SDR and no UI dependencies. Input is a block of complex64 IQ,
output is decoded messages. Every rule here is checked against public sample
messages in ``tests/test_modes.py``.
"""

import math
import threading
import time
from collections import deque

import numpy as np

# 4 MSPS: one 0.5 us half-bit maps to exactly 2 samples
FS = 4.0e6
HALF = 2
PREAMBLE = 16 * HALF
CHARSET = "#ABCDEFGHIJKLMNOPQRSTUVWXYZ#####_###############0123456789######"


# ------------------------------------------------------------------ Mode S
def checksum(bits):
    """24-bit Mode S CRC remainder; zero means the frame is intact."""
    rem = 0
    for b in bits:
        rem = (rem << 1) | b
        if rem & 0x1000000:
            rem ^= 0xFFF409
        rem &= 0xFFFFFF
    return rem


def bits_to_hex(bits):
    s = ""
    for i in range(0, len(bits), 4):
        v = 0
        for b in bits[i : i + 4]:
            v = (v << 1) | b
        s += "%X" % v
    return s


def _int(bits):
    v = 0
    for b in bits:
        v = (v << 1) | b
    return v


def nl(lat):
    """Number of CPR longitude zones at a given latitude."""
    if lat == 0:
        return 59
    lat = abs(lat)
    if lat >= 87.0:
        return 1
    a = 1 - math.cos(math.pi / 30.0)
    b = math.cos(math.radians(lat)) ** 2
    return int(math.floor(2 * math.pi / math.acos(1 - a / b)))


def cpr_global(ev, od):
    """Decode an even/odd CPR pair into an absolute position.

    Returns ``(lat, lon)`` or ``None`` when the pair is too far apart in time
    or lands in different longitude zones.
    """
    if abs(ev["t"] - od["t"]) > 12.0:
        return None
    lat_e = ev["lat"] / 131072.0
    lat_o = od["lat"] / 131072.0
    j = math.floor(59 * lat_e - 60 * lat_o + 0.5)
    rlat_e = 6.0 * ((j % 60) + lat_e)
    rlat_o = (360.0 / 59) * ((j % 59) + lat_o)
    if rlat_e >= 270:
        rlat_e -= 360
    if rlat_o >= 270:
        rlat_o -= 360
    if nl(rlat_e) != nl(rlat_o):
        return None
    n = nl(rlat_e)
    m = math.floor(ev["lon"] * (n - 1) / 131072.0 - od["lon"] * n / 131072.0 + 0.5)
    if od["t"] > ev["t"]:
        # Odd frames use NL-1 longitude zones, not NL.
        lat = rlat_o
        ni = max(nl(rlat_o) - 1, 1)
        lon = (360.0 / ni) * ((m % ni) + od["lon"] / 131072.0)
    else:
        lat = rlat_e
        ni = max(nl(rlat_e), 1)
        lon = (360.0 / ni) * ((m % ni) + ev["lon"] / 131072.0)
    if lon >= 180:
        lon -= 360
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return None
    return lat, lon


def decode_msg(bits):
    """Parse a frame into a dict.

    Position is not resolved here: it needs an even/odd pair, so the caller
    hands ``cpr`` to :func:`cpr_global` once both halves arrive.
    """
    df = _int(bits[:5])
    d = {"df": df, "n": len(bits), "t": time.time()}
    if df not in (17, 18) or len(bits) < 112:
        return d
    d["icao"] = bits_to_hex(bits[8:32])
    me = bits[32:88]
    tc = _int(me[:5])
    d["tc"] = tc
    if 1 <= tc <= 4:
        cs = "".join(CHARSET[_int(me[8 + i * 6 : 14 + i * 6])] for i in range(8))
        d["callsign"] = cs.replace("_", " ").strip()
        d["category"] = _int(me[5:8])
    elif 9 <= tc <= 18:
        ac12 = _int(me[8:20])
        if ac12 & 0x10:
            d["alt"] = (((ac12 & 0x0FE0) >> 1) | (ac12 & 0x000F)) * 25 - 1000
        # me[21] is the CPR odd/even flag (0 = even, 1 = odd).
        d["cpr"] = (_int(me[22:39]), _int(me[39:56]), me[21])
    elif tc == 19:
        sub = _int(me[5:8])
        if sub in (1, 2):
            ew, ns = _int(me[14:24]), _int(me[25:35])
            if ew and ns:
                vx = (ew - 1) * (1 if me[13] == 0 else -1)
                vy = (ns - 1) * (1 if me[24] == 0 else -1)
                d["gs"] = math.hypot(vx, vy)
                d["trk"] = math.degrees(math.atan2(vx, vy)) % 360.0
            vr = _int(me[37:46])
            if vr:
                d["vs"] = (vr - 1) * 64 * (1 if me[36] == 0 else -1)
    return d


def chunk_pulses(m, thr):
    """Find preamble candidates: four pulses at 0, 2, 7 and 9 half-bits."""
    n = len(m) - 16 * HALF
    if n <= 0:
        return np.array([], dtype=int)
    s = np.minimum(
        np.minimum(m[0:n], m[2 * HALF : 2 * HALF + n]),
        np.minimum(m[7 * HALF : 7 * HALF + n], m[9 * HALF : 9 * HALF + n]),
    )
    idx = np.flatnonzero(s > thr)
    keep, last = [], -(10**9)
    for i in idx:
        if i - last > 100 * FS / 1e6:
            keep.append(int(i))
        last = i
    return keep


def try_decode(m, i0, nbits=112):
    """Slice bits at candidate ``i0`` and return them only if the CRC passes."""
    base = i0 + PREAMBLE
    if base + 2 * HALF * nbits > len(m):
        return None
    for shift in (0, 1):
        b0 = base + shift
        if b0 + 2 * HALF * nbits > len(m):
            continue
        idx = b0 + 2 * HALF * np.arange(nbits)[:, None] + np.arange(2 * HALF)[None, :]
        w = m[idx]
        bits = (w[:, :HALF].sum(axis=1) > w[:, HALF:].sum(axis=1)).astype(np.int8).tolist()
        if checksum(bits) == 0:
            return bits
    return None


# ------------------------------------------------------------------ state
class Store:
    """Thread-safe snapshot of what has been heard so far."""

    def __init__(self):
        self.lock = threading.Lock()
        self.planes = {}  # icao -> dict
        self.total = 0
        self.rate = 0.0
        self.rate_buf = deque(maxlen=10)
        self.status = "starting"
        self.t0 = time.time()

    def snapshot(self):
        with self.lock:
            return (dict((k, dict(v)) for k, v in self.planes.items()), self.total, self.rate, self.status)


def update_plane(st, d):
    """Merge one decoded frame into the shared aircraft table."""
    icao = d["icao"]
    with st.lock:
        p = st.planes.setdefault(icao, {"n": 0, "trail": deque(maxlen=40), "first": time.time(), "icao": icao})
        p["n"] += 1
        p["seen"] = time.time()
        for k in ("callsign", "alt", "gs", "trk", "vs", "category", "tc"):
            if d.get(k) is not None:
                p[k] = d[k]
        if d.get("cpr") is not None:
            latc, lonc, odd = d["cpr"]
            p["odd" if odd else "even"] = {"lat": latc, "lon": lonc, "t": d["t"]}
            ev, od = p.get("even"), p.get("odd")
            if ev and od:
                pos = cpr_global(ev, od)
                if pos:
                    lat, lon = pos
                    if not p["trail"] or abs(p["trail"][-1][0] - lat) + abs(p["trail"][-1][1] - lon) > 0.002:
                        p["trail"].append((lat, lon))
                    p["lat"], p["lon"] = lat, lon
        p["last_hex"] = d.get("hex", "")
