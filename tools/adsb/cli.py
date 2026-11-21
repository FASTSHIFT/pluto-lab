# -*- coding: utf-8 -*-
"""ADS-B command line receiver: capture N seconds, print frames, dump CSV/PNG.

python tools/adsb/cli.py --seconds 60 --gain 62
python tools/adsb/cli.py --selftest
"""

import argparse
import csv
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from sdr import paths

paths.setup()

import numpy as np

from sdr.modes import FS, Store, bits_to_hex, checksum, chunk_pulses, cpr_global, decode_msg, try_decode, update_plane


def selftest():
    """Validate the decoder against public sample frames."""

    def h2b(h):
        b = []
        for ch in h:
            v = int(ch, 16)
            b += [(v >> 3) & 1, (v >> 2) & 1, (v >> 1) & 1, v & 1]
        return b

    ok = True

    d = decode_msg(h2b("8D4840D6202CC371C32CE0576098"))
    good = checksum(h2b("8D4840D6202CC371C32CE0576098")) == 0
    good = good and d.get("callsign") == "KLM1023"
    ok &= good
    print("callsign : %-8r %s" % (d.get("callsign"), "OK" if good else "FAIL"))

    d = decode_msg(h2b("8D40621D58C382D690C8AC2863A7"))
    good = d.get("alt") == 38000
    ok &= good
    print("altitude : %-8s %s" % (d.get("alt"), "OK" if good else "FAIL"))

    ev = decode_msg(h2b("8D40621D58C382D690C8AC2863A7"))
    od = decode_msg(h2b("8D40621D58C386435CC412692AD6"))
    ev["t"] = time.time() + 0.5
    od["t"] = time.time()
    pos = cpr_global(
        {"lat": ev["cpr"][0], "lon": ev["cpr"][1], "t": ev["t"]},
        {"lat": od["cpr"][0], "lon": od["cpr"][1], "t": od["t"]},
    )
    good = bool(pos) and abs(pos[0] - 52.25720) < 1e-4 and abs(pos[1] - 3.91937) < 1e-4
    ok &= good
    if pos:
        print("position : %.5f, %.5f  %s" % (pos[0], pos[1], "OK" if good else "FAIL"))
    else:
        print("position : unresolved  FAIL")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--gain", type=float, default=62.0)
    ap.add_argument("--out", default="adsb.png")
    ap.add_argument("--csv", default="adsb_messages.csv")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return 0 if selftest() else 1

    import adi

    sdr = adi.Pluto(uri="ip:192.168.2.1")
    sdr.sample_rate = int(FS)
    sdr.rx_rf_bandwidth = int(2.4e6)
    sdr.rx_buffer_size = 2**17
    sdr.gain_control_mode_chan0 = "manual"
    sdr.rx_hardwaregain_chan0 = args.gain
    sdr.rx_lo = int(1090e6)

    st = Store()
    print("=" * 68)
    print(" ADS-B receiving | 1090 MHz | %.0f dB | %.1f MSPS" % (args.gain, FS / 1e6))
    print("=" * 68)

    t0 = time.time()
    rows = []
    plot_env = None
    while time.time() - t0 < args.seconds:
        x = np.asarray(sdr.rx()).astype(np.complex64) / 2048.0
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
            d["t"] = time.time() - t0
            update_plane(st, d)
            rows.append(d)
            if plot_env is None and d.get("df") == 17:
                seg = m[max(0, i0 - 40) : i0 + 32 + 448 + 40]
                plot_env = seg / (seg.max() + 1e-12)
            print(
                "  %6.1fs  %s  DF%-2d %-8s %s"
                % (
                    d["t"],
                    d["hex"],
                    d["df"],
                    d.get("callsign") or "",
                    ("%d ft" % d["alt"]) if d.get("alt") is not None else "",
                )
            )

    dur = max(time.time() - t0, 1e-6)
    planes, total, rate, _ = st.snapshot()
    print()
    print("=" * 68)
    print(" done: %.1f s, %d frames (%.1f/s), %d aircraft" % (dur, len(rows), len(rows) / dur, len(planes)))
    print("=" * 68)

    if planes:
        print("\n  ICAO     CALLSIGN   ALT(ft)  FRAMES")
        for icao, p in sorted(planes.items(), key=lambda kv: -kv[1]["n"])[:30]:
            print("  %-8s %-10s %8s  %5d" % (icao, p.get("callsign", "-"), p.get("alt", "-"), p["n"]))

    if rows and args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["time_s", "hex", "df", "icao", "callsign", "alt_ft"])
            for r in rows:
                w.writerow(
                    [round(r["t"], 3), r["hex"], r["df"], r.get("icao", ""), r.get("callsign", ""), r.get("alt", "")]
                )
        print("\nframes saved to: %s" % args.csv)

    if args.out:
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(12, 5), dpi=120)
            if plot_env is not None:
                t = np.arange(len(plot_env)) / (FS / 1e6)
                ax.plot(t, plot_env, lw=1.0, color="#1f6feb", drawstyle="steps-post")
                ax.set_title("Decoded ADS-B message (%s)" % rows[0]["hex"])
                ax.set_xlabel("time (us)")
            else:
                ax.set_title("no message decoded")
            fig.tight_layout()
            fig.savefig(args.out)
            print("waveform saved to: %s" % args.out)
        except ImportError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
