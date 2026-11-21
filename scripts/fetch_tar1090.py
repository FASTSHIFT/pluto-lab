# -*- coding: utf-8 -*-
"""Fetch the tar1090 frontend and apply our local patches.

tar1090's html tree is GPL-2.0 and 300+ files, so it is **not** committed.
This script pulls the release archive into ``web/`` and makes two edits:

1. ``layers.js`` - add AMap base layers (OSM is not reachable from here)
2. ``config.js`` - default to AMap, set the site name and zoom level

    python scripts/fetch_tar1090.py
"""

import io
import os
import tarfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")

URL = "https://github.com/wiedehopf/tar1090/archive/refs/heads/master.tar.gz"

AMAP_LAYERS = """
        world.push(new ol.layer.Tile({
            source: new ol.source.XYZ({
                url: "https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}",
                attributions: '\\u00a9 AMap',
                attributionsCollapsible: false,
                maxZoom: 18,
                transition: tileTransition,
            }),
            name: 'amap',
            title: 'AMap',
            type: 'base',
        }));
        world.push(new ol.layer.Tile({
            source: new ol.source.XYZ({
                url: "https://webst01.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}",
                attributions: '\\u00a9 AMap',
                attributionsCollapsible: false,
                maxZoom: 18,
                transition: tileTransition,
            }),
            name: 'amap_sat',
            title: 'AMap Satellite',
            type: 'base',
        }));"""

CONFIG_EXTRA = """
// --------------------------------------------------------
// Local overrides written by scripts/fetch_tar1090.py
// --------------------------------------------------------
MapType_tar1090 = "amap";
SiteShow = true;
SiteName = "Home";
DefaultZoomLvl = 9;
PageName = "pluto-lab ADS-B";
DisplayUnits = "metric";
altitudeUnits = "nautical";
darkModeDefault = false;
"""


def main():
    print("downloading tar1090 ...")
    req = urllib.request.Request(URL, headers={"User-Agent": "pluto-lab/1.0"})
    data = urllib.request.urlopen(req, timeout=180).read()
    tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")
    os.makedirs(WEB, exist_ok=True)
    n = 0
    for m in tf.getmembers():
        if "/html/" not in m.name or not m.isfile():
            continue
        rel = m.name.split("/html/", 1)[1]
        out = os.path.join(WEB, rel)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as f:
            f.write(tf.extractfile(m).read())
        n += 1
    print("  extracted %d files into web/" % n)

    # 1) add the AMap layers
    p = os.path.join(WEB, "layers.js")
    s = open(p, encoding="utf-8").read()
    if "name: 'amap'" not in s:
        i = s.index("name: 'esri',")
        j = s.index("}));", i) + len("}));")
        s = s[:j] + AMAP_LAYERS + s[j:]
        open(p, "w", encoding="utf-8", newline="\n").write(s)
        print("  layers.js: AMap layers added")

    # 2) append our config overrides
    c = os.path.join(WEB, "config.js")
    cs = open(c, encoding="utf-8").read()
    if 'MapType_tar1090 = "amap"' not in cs:
        open(c, "a", encoding="utf-8", newline="\n").write(CONFIG_EXTRA)
        print("  config.js: local overrides written")

    print("\ndone. start the server with: python tools/adsb/web.py --lat <lat> --lon <lon>")


if __name__ == "__main__":
    main()
