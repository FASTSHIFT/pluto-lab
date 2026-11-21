# -*- coding: utf-8 -*-
"""Serve decoded ADS-B data to the tar1090 frontend.

    python tools/adsb/web.py --lat 40.0689 --lon 116.3072
    open http://127.0.0.1:8080/

The backend does exactly three things:

1. receive 1090 MHz using the decoders in ``sdr/``
2. emit ``data/aircraft.json`` in the schema readsb uses
3. serve the static files in ``web/`` (the tar1090 frontend)

tar1090 has no idea the data comes from a Pluto. Swapping the radio means
swapping ``sdr/source.py`` and nothing else.
"""

import argparse
import json
import os
import sys
import threading
import time
import http.server
import socketserver
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from sdr import paths, modes, source, geo  # decoder / state / rx loop / datum

paths.setup()

WEB = os.path.join(ROOT, "web")
MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".geojson": "application/geo+json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".txt": "text/plain; charset=utf-8",
}

REF = [None, None]
STATE = {"store": None, "start": time.time()}

# AMap tiles are GCJ-02 while ADS-B reports WGS-84, so convert by default.
# Pass --no-gcj when you switch to a WGS-84 basemap such as OSM or ESRI.
GCJ = True


def aircraft_json():
    st = STATE["store"]
    planes, total, rate, status = st.snapshot()
    now = time.time()
    out = []
    for icao, p in planes.items():
        age = now - p.get("seen", now)
        if age > 120:
            continue
        d = {
            "hex": icao.lower(),
            "messages": p.get("n", 0),
            "seen": round(age, 1),
            "rssi": -20.0,
        }
        cs = p.get("callsign")
        if cs:
            d["flight"] = cs
        if p.get("alt") is not None:
            d["alt_baro"] = p["alt"]
        if p.get("gs") is not None:
            d["gs"] = round(p["gs"], 1)
        if p.get("trk") is not None:
            d["track"] = round(p["trk"], 1)
        if p.get("vs") is not None:
            d["baro_rate"] = p["vs"]
        if p.get("lat") is not None:
            lat, lon = p["lat"], p["lon"]
            if GCJ:
                lat, lon = geo.wgs2gcj(lat, lon)
            d["lat"] = round(lat, 6)
            d["lon"] = round(lon, 6)
            d["seen_pos"] = round(now - p.get("seen", now), 1)
        out.append(d)
    return {"now": now, "messages": total, "aircraft": out}


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if "json" in ctype else "max-age=60")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _static(self, rel):
        rel = rel.replace("..", "")
        path = os.path.join(WEB, rel.replace("/", os.sep))
        if not os.path.isfile(path):
            self._send(404, "not found", "text/plain")
            return
        ext = os.path.splitext(path)[1].lower()
        with open(path, "rb") as f:
            self._send(200, f.read(), MIME.get(ext, "application/octet-stream"))

    def do_GET(self):
        p = urllib.parse.unquote(self.path.split("?")[0])
        try:
            if p == "/data/aircraft.json":
                return self._json(aircraft_json())
            if p == "/data/receiver.json":
                rlat, rlon = REF[0], REF[1]
                if GCJ and rlat is not None:
                    rlat, rlon = geo.wgs2gcj(rlat, rlon)
                return self._json(
                    {
                        "version": "pluto-adsb",
                        "refresh": 1000,
                        "lat": rlat,
                        "lon": rlon,
                        "history": 0,
                    }
                )
            if (
                p.startswith("/data/")
                or p.startswith("/chunks/")
                or p.startswith("/globe_history/")
                or p.startswith("/heatmap/")
            ):
                return self._json({"now": time.time()}, 404)
            if p in ("/", ""):
                return self._static("index.html")
            return self._static(p.lstrip("/"))
        except Exception as e:
            try:
                self._send(500, str(e), "text/plain")
            except Exception:
                pass


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    global GCJ
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, default=None)
    ap.add_argument("--lon", type=float, default=None)
    ap.add_argument("--gain", type=float, default=66.0)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--no-gcj", action="store_true", help="skip the WGS-84 -> GCJ-02 shift (OSM/ESRI basemaps)")
    args = ap.parse_args()

    GCJ = not args.no_gcj
    REF[0], REF[1] = args.lat, args.lon

    st = modes.Store()
    STATE["store"] = st
    stop = threading.Event()
    threading.Thread(target=source.rx_loop, args=(st, stop, args.gain), daemon=True).start()

    srv = Server(("127.0.0.1", args.port), Handler)
    print("=" * 62)
    print(" tar1090 frontend : http://127.0.0.1:%d/" % args.port)
    print(" data endpoint    : /data/aircraft.json")
    print(" device           : PlutoSDR 1090 MHz, gain %.0f dB" % args.gain)
    print(" datum            : %s" % ("WGS-84 -> GCJ-02 (AMap tiles)" if GCJ else "WGS-84 as-is"))
    print("=" * 62)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        stop.set()
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
