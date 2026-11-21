#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Spectrum scanner and audio demodulator for PlutoSDR.

    python tools/spectrum/scan.py info
    python tools/spectrum/scan.py scan --preset wide
    python tools/spectrum/scan.py scan --start 85 --stop 180 --out spectrum.png
    python tools/spectrum/scan.py fm --freq 97.4 --seconds 12 --out station.wav

Requires pyadi-iio (see scripts/setup_windows.py for the libiio DLL).
"""

import argparse
import os
import sys
import time
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from sdr import paths

paths.setup()

import numpy as np

FULL_SCALE = 2048.0  # Pluto has a 12-bit ADC; raw codes span +/- 2048

# ---------------------------------------------------------------- band labels
BANDS = [
    (87.5, 108.0, "FM broadcast"),
    (108.0, 118.0, "air nav VOR/ILS"),
    (118.0, 137.0, "airband AM (tower/approach)"),
    (137.0, 138.5, "weather sat NOAA/Meteor"),
    (144.0, 146.0, "amateur 2m"),
    (145.8, 146.0, "ISS SSTV / amateur sat"),
    (151.0, 174.0, "business radio / land mobile"),
    (156.0, 163.0, "maritime VHF"),
    (161.9, 162.1, "AIS"),
    (174.0, 240.0, "DAB / DVB-T"),
    (400.0, 470.0, "PMR / TETRA / trunked"),
    (430.0, 440.0, "amateur 70cm"),
    (446.0, 446.2, "PMR446"),
    (409.7, 410.1, "public walkie-talkie"),
    (470.0, 510.0, "LoRa / smart meters"),
    (902.0, 928.0, "ISM 902"),
    (1085.0, 1095.0, "ADS-B 1090"),
    (1570.0, 1580.0, "GPS L1"),
    (1610.0, 1630.0, "Iridium"),
    (2400.0, 2483.5, "WiFi / BLE / drone"),
]

PRESETS = {
    "wide": (85.0, 180.0, 40.0),
    "fm": (87.0, 109.0, 40.0),
    "air": (115.0, 140.0, 40.0),
    "sat": (136.0, 139.0, 45.0),
    "2m": (143.0, 148.0, 40.0),
    "ism24": (2390.0, 2500.0, 45.0),
    "adsb": (1085.0, 1095.0, 40.0),
}


def band_name(f):
    for a, b, n in BANDS:
        if a <= f < b:
            return n
    return ""


# ---------------------------------------------------------------- device
def connect(uri=None):
    import adi

    uris = [uri] if uri else ["ip:192.168.2.1", "usb:", "ip:pluto.local"]
    err = None
    for u in uris:
        try:
            sdr = adi.Pluto(uri=u)
            _ = sdr.sample_rate  # force one real transaction
            return sdr, u
        except Exception as e:
            err = e
    raise SystemExit("cannot reach PlutoSDR: %s" % err)


def set_gain(sdr, g):
    try:
        sdr.gain_control_mode_chan0 = "manual"
    except Exception:
        pass
    for attr in ("rx_hardwaregain_chan0", "rx_hardwaregain"):
        try:
            setattr(sdr, attr, g)
            return True
        except Exception:
            continue
    return False


def get_gain(sdr):
    for attr in ("rx_hardwaregain_chan0", "rx_hardwaregain"):
        try:
            return getattr(sdr, attr)
        except Exception:
            continue
    return None


def safe(fn, default="?"):
    try:
        return fn()
    except Exception:
        return default


# ---------------------------------------------------------------- info
def cmd_info(args):
    sdr, uri = connect(args.uri)
    print("=" * 62)
    print("PlutoSDR connected:", uri)
    print("=" * 62)
    print("  libiio version :", safe(lambda: sdr.ctx.version))
    print("  hw_model       :", safe(lambda: sdr.ctx.attrs["hw_model"] if "hw_model" in sdr.ctx.attrs else "?"))
    print("  sample rate    :", safe(lambda: sdr.sample_rate))
    print("  RX LO          :", safe(lambda: sdr.rx_lo))
    print("  RX bandwidth   :", safe(lambda: sdr.rx_rf_bandwidth))
    print("  RX gain (man.) :", get_gain(sdr))
    print("  RX channels    :", safe(lambda: len(sdr.rx_enabled_channels)))
    print("  TX channels    :", safe(lambda: len(sdr.tx_enabled_channels)))
    print()
    print("  --- hardware ---")
    try:
        for d in sdr.ctx.devices:
            print("  [%s]" % d.name)
    except Exception:
        pass
    print()
    print("  tip: a whip around 50-75 cm is best suited for 85-180 MHz.")
    return 0


# ---------------------------------------------------------------- capture
def grab(sdr, freq, sr, nbuf=4, buf=2**15):
    sdr.rx_lo = int(freq)
    sdr.rx_rf_bandwidth = int(min(sr, 56e6))
    sdr.rx_buffer_size = buf
    time.sleep(0.02)
    chunks = []
    for _ in range(nbuf):
        chunks.append(np.asarray(sdr.rx()).astype(np.complex64))
    # Pluto returns raw 12-bit codes; normalise to full scale.
    return np.concatenate(chunks) / FULL_SCALE


def psd_db(x, sr, nfft):
    w = np.hanning(nfft)
    n = len(x) // nfft
    if n < 1:
        return None
    acc = np.zeros(nfft)
    for i in range(n):
        seg = x[i * nfft : (i + 1) * nfft] * w
        X = np.fft.fftshift(np.fft.fft(seg))
        acc += np.abs(X) ** 2
    acc /= n
    acc /= nfft * np.sum(w**2)
    freqs = np.fft.fftshift(np.fft.fftfreq(nfft, 1.0 / sr))
    return freqs, 10.0 * np.log10(acc + 1e-20)


# ---------------------------------------------------------------- scan
def cmd_scan(args):
    if args.preset:
        if args.preset not in PRESETS:
            raise SystemExit("unknown preset: %s (choose from: %s)" % (args.preset, ", ".join(PRESETS)))
        start, stop, gain = PRESETS[args.preset]
        if start is None:
            start = args.start
            stop = args.stop
            gain = args.gain
    else:
        start, stop, gain = args.start, args.stop, args.gain

    sdr, uri = connect(args.uri)
    sr = float(args.sr)
    nfft = 4096
    set_gain(sdr, gain)

    span = sr * 0.65  # keep the middle 65%, overlap 35%
    total_hz = (stop - start) * 1e6
    nsteps = max(1, int(np.ceil(total_hz / span)))
    step = total_hz / nsteps / 1e6

    print("device: %s | %.2f MSPS | gain %.1f dB" % (uri, sr / 1e6, gain))
    print("scanning %.1f - %.1f MHz | %d steps x %.2f MHz\n" % (start, stop, nsteps, step))

    grid_step = 2000.0
    grid = np.arange(start * 1e6, stop * 1e6, grid_step)
    spec = np.full(len(grid), -200.0)

    for i in range(nsteps):
        fc = start * 1e6 + step * 1e6 * (i + 0.5)
        try:
            x = grab(sdr, fc, sr, nbuf=args.nbuf)
        except Exception as e:
            print("  [%2d/%d] %.3f MHz capture failed: %s" % (i + 1, nsteps, fc / 1e6, e))
            continue
        out = psd_db(x, sr, nfft)
        if out is None:
            continue
        f, p = out
        m = np.abs(f) < sr * 0.35  # drop the filter roll-off on both edges
        m &= np.abs(f) > 4e3  # drop the LO leakage spike at DC
        idx = np.round((f[m] + fc - start * 1e6) / grid_step).astype(int)
        ok = (idx >= 0) & (idx < len(grid))
        np.maximum.at(spec, idx[ok], p[m][ok])
        print(
            "  [%2d/%d] centre %8.3f MHz   floor %6.1f dB   peak %6.1f dB"
            % (i + 1, nsteps, fc / 1e6, np.median(p), np.max(p))
        )

    valid = spec > -190
    if not np.any(valid):
        print("\nno usable data, check the antenna and the device")
        return 1

    # Interpolate the few stitching gaps so the plot has no vertical stripes.
    missing = ~valid
    if np.any(missing):
        xi = np.arange(len(spec))
        spec[missing] = np.interp(xi[missing], xi[valid], spec[valid])
        valid = np.ones(len(spec), dtype=bool)

    if args.dump:
        np.savez(args.dump, grid_hz=grid, spec_db=spec, step_hz=step * 1e6, start_hz=start * 1e6, sr_hz=sr)
        print("raw spectrum saved to:", args.dump)

    floor = np.median(spec[valid])
    thr = floor + args.threshold
    print("\nfloor %.1f dBFS | threshold %.1f dBFS (+%.0f dB)" % (floor, thr, args.threshold))

    # Peak picking: every run of bins above the threshold counts once.
    peaks = []
    above = spec > thr
    i = 0
    while i < len(spec):
        if above[i]:
            j = i
            while j < len(spec) and above[j]:
                j += 1
            k = i + int(np.argmax(spec[i:j]))
            peaks.append((grid[k] / 1e6, spec[k], j - i))
            i = j
        else:
            i += 1

    peaks.sort(key=lambda t: -t[1])
    peaks = peaks[: args.top]

    print("\n" + "=" * 70)
    print("  #   frequency(MHz)   power(dBFS)   SNR(dB)   likely service")
    print("=" * 70)
    rows = []
    for n, (f, p, _) in enumerate(peaks, 1):
        bn = band_name(f) or "-"
        print("  %2d  %12.4f  %11.1f  %8.1f   %s" % (n, f, p, p - floor, bn))
        rows.append((f, p, p - floor, bn))
    print("=" * 70)

    if args.csv:
        with open(args.csv, "w", encoding="utf-8") as fh:
            fh.write("freq_mhz,power_dbfs,snr_db,band\n")
            for f, p, s, bn in rows:
                fh.write("%.4f,%.1f,%.1f,%s\n" % (f, p, s, bn))
        print("peaks saved to:", args.csv)

    if args.out:
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(14, 6), dpi=130)
            ax.plot(grid / 1e6, spec, lw=0.7, color="#1f6feb")
            ax.set_facecolor("#0d1117")
            fig.patch.set_facecolor("#0d1117")
            ax.tick_params(colors="#c9d1d9")
            for sp in ax.spines.values():
                sp.set_color("#30363d")
            ax.set_xlabel("Frequency (MHz)", color="#c9d1d9")
            ax.set_ylabel("Power (dBFS)", color="#c9d1d9")
            ax.set_title("PlutoSDR spectrum  %.0f-%.0f MHz" % (start, stop), color="#c9d1d9")
            ax.grid(True, color="#21262d", lw=0.5)
            ax.set_ylim(floor - 6, max(np.max(spec[valid]) + 8, floor + 20))
            for f, p, s, bn in rows[:8]:
                ax.annotate(
                    "%.2f" % f,
                    (f, p),
                    textcoords="offset points",
                    xytext=(0, 6),
                    ha="center",
                    fontsize=7,
                    color="#f0883e",
                )
            fig.tight_layout()
            fig.savefig(args.out, facecolor=fig.get_facecolor())
            print("plot saved to:", args.out)
        except ImportError:
            print("(matplotlib not installed, skipping the plot)")

    print()
    best = rows[0] if rows else None
    if best:
        print("strongest signal %.3f MHz (%s, %.0f dB above the floor)" % (best[0], best[3], best[2]))
        if 87.5 <= best[0] <= 108:
            print("-> that is an FM station. Listen with: python tools/spectrum/scan.py fm --freq %.2f" % best[0])
    return 0


# ---------------------------------------------------------------- audio
def cmd_fm(args):
    sdr, uri = connect(args.uri)
    sr = 1.92e6  # divides exactly by 40 to 48 kHz
    set_gain(sdr, args.gain)
    sdr.rx_rf_bandwidth = int(200e3)
    sdr.rx_buffer_size = 2**16

    nbuf = int(np.ceil(args.seconds * sr / sdr.rx_buffer_size))
    print("tuning %.3f MHz for %d s at gain %.0f dB ..." % (args.freq, args.seconds, args.gain))
    sdr.rx_lo = int(args.freq * 1e6)
    time.sleep(0.05)

    chunks = []
    t0 = time.time()
    for i in range(nbuf):
        chunks.append(np.asarray(sdr.rx()).astype(np.complex64))
        print("  %d/%d  %.1fs" % (i + 1, nbuf, time.time() - t0), end="\r")
    print()
    x = np.concatenate(chunks) / FULL_SCALE

    lvl = 20 * np.log10(np.sqrt(np.mean(np.abs(x) ** 2)) + 1e-12)
    print("input level: %.1f dBFS" % lvl)
    if lvl < -60:
        print("very weak; wrong frequency, bad antenna pointing, or gain too low")

    x = x - np.mean(x)
    y = _demod(x, sr, mode=getattr(args, "mode", "fm"), deemphasis=args.deemphasis)

    pcm = (y * 32767).astype(np.int16)
    with wave.open(args.out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(pcm.tobytes())

    print("saved: %s  (%.1f s, 48 kHz mono)" % (args.out, len(pcm) / 48000.0))
    return 0


def _demod(x, sr, mode="fm", deemphasis=True):
    """Discriminate FM or envelope-detect AM, then resample to 48 kHz mono."""
    if mode == "fm":
        d = x[1:] * np.conj(x[:-1])
        y = np.angle(d).astype(np.float64)
    else:  # AM: envelope detector
        y = np.abs(x).astype(np.float64)
        y -= np.mean(y)

    dec = int(round(sr / 48000.0))
    try:
        from scipy import signal as sps

        k1 = 8 if dec % 8 == 0 else 1
        y = sps.decimate(y, k1, ftype="iir", zero_phase=True)
        k2 = dec // k1
        if k2 > 1:
            y = sps.decimate(y, k2, ftype="iir", zero_phase=True)
        if mode == "fm" and deemphasis:
            a = float(np.exp(-1.0 / (48000.0 * 50e-6)))
            y = sps.lfilter([1.0 - a], [1.0, -a], y)
    except ImportError:  # no scipy: fall back to a boxcar
        n = len(y) // dec
        y = y[: n * dec].reshape(n, dec).mean(axis=1)
        if mode == "fm" and deemphasis:
            a = float(np.exp(-1.0 / (48000.0 * 50e-6)))
            out = np.empty_like(y)
            prev = 0.0
            for i in range(len(y)):
                prev = a * prev + (1 - a) * y[i]
                out[i] = prev
            y = out

    y = y - np.mean(y)
    rms = np.sqrt(np.mean(y**2)) + 1e-12
    return np.clip(y / rms * 0.25, -1.0, 1.0)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="PlutoSDR spectrum and audio tool")
    ap.add_argument("--uri", default=None, help="device URI, default ip:192.168.2.1")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info", help="print device information")

    p = sub.add_parser("scan", help="sweep a band and list peaks")
    p.add_argument("--preset", default=None, choices=list(PRESETS))
    p.add_argument("--start", type=float, default=85.0, help="start MHz")
    p.add_argument("--stop", type=float, default=180.0, help="stop MHz")
    p.add_argument("--sr", type=float, default=2e6, help="per-step sample rate in Hz (USB2 limit, keep under 3M)")
    p.add_argument("--gain", type=float, default=40.0)
    p.add_argument("--threshold", type=float, default=8.0, help="dB above the noise floor to count as a signal")
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--nbuf", type=int, default=4)
    p.add_argument("--out", default="spectrum.png")
    p.add_argument("--csv", default="peaks.csv")
    p.add_argument("--dump", default=None, help="save the stitched spectrum as npz")

    p = sub.add_parser("fm", help="demodulate an FM channel to a wav file")
    p.add_argument("--freq", type=float, required=True, help="MHz")
    p.add_argument("--seconds", type=float, default=10.0)
    p.add_argument("--gain", type=float, default=40.0)
    p.add_argument("--deemphasis", action="store_true", default=True)
    p.add_argument("--out", default="station.wav")
    p.set_defaults(mode="fm")

    p = sub.add_parser("am", help="demodulate an AM channel (airband)")
    p.add_argument("--freq", type=float, required=True, help="MHz")
    p.add_argument("--seconds", type=float, default=10.0)
    p.add_argument("--gain", type=float, default=45.0)
    p.add_argument("--deemphasis", action="store_true", default=False)
    p.add_argument("--out", default="am.wav")
    p.set_defaults(mode="am")

    args = ap.parse_args()
    return {"info": cmd_info, "scan": cmd_scan, "fm": cmd_fm, "am": cmd_fm}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
