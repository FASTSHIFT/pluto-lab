# -*- coding: utf-8 -*-
"""Windows bootstrap: download the official libiio binaries.

pyadi-iio needs ``libiio.dll`` on Windows and pip does not ship it, so we pull
the Analog Devices release archive and unpack the VS2019 x64 build:

    python scripts/setup_windows.py
"""

import io
import os
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "libiio")

URL = "https://github.com/analogdevicesinc/libiio/releases/download/v0.25/libiio-0.25-gb6028fd-windows.zip"
SUBDIR = "Windows-VS-2019-x64"
KEEP = (".dll", ".exe", ".lib", ".exp")


def fetch(url):
    print("downloading %s" % url)
    req = urllib.request.Request(url, headers={"User-Agent": "pluto-lab-setup/1.0"})
    data = urllib.request.urlopen(req, timeout=180).read()
    print("  %.1f MB" % (len(data) / 1e6))
    return data


def main():
    if os.path.isdir(DEST) and any(f.endswith(".dll") for f in os.listdir(DEST)):
        print("libiio/ already present, skipping (delete the directory to redo)")
    else:
        z = zipfile.ZipFile(io.BytesIO(fetch(URL)))
        os.makedirs(DEST, exist_ok=True)
        n = 0
        for m in z.namelist():
            if not m.startswith(SUBDIR + "/") or m.endswith("/"):
                continue
            name = m.split("/", 1)[1]
            if not name.lower().endswith(KEEP):
                continue
            with open(os.path.join(DEST, name), "wb") as f:
                f.write(z.read(m))
            n += 1
        print("unpacked %d files into %s" % (n, DEST))

    print("""
Next steps:

    python -m venv .venv
    .venv\\Scripts\\activate
    pip install -e ".[full]"

    python scripts/fetch_tar1090.py     # only if you want the web UI
    python tools/adsb/cli.py --selftest
""")


if __name__ == "__main__":
    main()
