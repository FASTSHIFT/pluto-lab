# -*- coding: utf-8 -*-
"""SDR capture plus the real-time decode loop.

This is the only module that talks to pyadi-iio. Swapping hardware
(HackRF / RTL-TCP / a recorded IQ file) means writing another class whose
``read()`` returns a complex64 block and pointing the loop at it.
"""

import time

import numpy as np

from . import paths
from .modes import FS, Store, bits_to_hex, chunk_pulses, decode_msg, try_decode, update_plane

FULL_SCALE = 2048.0  # Pluto has a 12-bit ADC; raw codes span +/- 2048


# ------------------------------------------------------------------ rx loop
def rx_loop(st, stop, gain):
    """Capture 1090 MHz and feed decoded frames into ``st`` until ``stop`` is set."""
    paths.setup()
    import adi

    try:
        sdr = adi.Pluto(uri="ip:192.168.2.1")
        sdr.sample_rate = int(FS)
        sdr.rx_rf_bandwidth = int(2.4e6)
        sdr.rx_buffer_size = 2**17
        sdr.gain_control_mode_chan0 = "manual"
        sdr.rx_hardwaregain_chan0 = gain
        sdr.rx_lo = int(1090e6)
    except Exception as e:
        with st.lock:
            st.status = "device error: %s" % e
        return
    with st.lock:
        st.status = "receiving  1090 MHz  %.0f dB" % gain
    tick = time.time()
    cnt = 0
    while not stop.is_set():
        try:
            x = np.asarray(sdr.rx()).astype(np.complex64) / 2048.0
        except Exception:
            continue
        m = np.abs(x)
        thr = (np.median(m) + 1e-12) * 5.0
        for i0 in chunk_pulses(m, thr):
            bits = try_decode(m, i0, 112)
            if bits is None:
                continue
            d = decode_msg(bits)
            d["hex"] = bits_to_hex(bits)
            if not d.get("icao"):
                continue
            cnt += 1
            update_plane(st, d)
        now = time.time()
        if now - tick >= 1.0:
            with st.lock:
                st.total += cnt
                st.rate_buf.append(cnt / (now - tick))
                st.rate = sum(st.rate_buf) / len(st.rate_buf)
            cnt = 0
            tick = now
