# -*- coding: utf-8 -*-
"""Map projections and datum shifts.

ADS-B positions are **WGS-84**, while most mainland Chinese tile providers
(AMap, Tencent, Baidu) serve **GCJ-02** tiles. Plotting one on the other
shifts everything by 300-600 m, which becomes obvious once you zoom in.

    lat, lon = wgs2gcj(40.0689, 116.3072)   # before drawing on an AMap tile
    lat, lon = gcj2wgs(lat, lon)            # before computing distances

International tile sets (OSM, ESRI) are WGS-84 and need no conversion.
"""

import math

# Krasovsky 1940 ellipsoid parameters used by the GCJ-02 transform
_A = 6378245.0
_EE = 0.00669342162296594323


def out_of_china(lat, lon):
    """GCJ-02 only applies inside mainland China; elsewhere return as-is."""
    return not (72.004 <= lon <= 137.8347 and 0.8293 <= lat <= 55.8271)


def _tf_lat(x, y):
    r = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    r += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    r += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    r += (160.0 * math.sin(y / 12.0 * math.pi) + 320.0 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return r


def _tf_lon(x, y):
    r = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    r += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    r += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    r += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return r


def wgs2gcj(lat, lon):
    """Convert WGS-84 to GCJ-02."""
    if out_of_china(lat, lon):
        return lat, lon
    dlat = _tf_lat(lon - 105.0, lat - 35.0)
    dlon = _tf_lon(lon - 105.0, lat - 35.0)
    rad = math.radians(lat)
    m = 1 - _EE * math.sin(rad) ** 2
    sm = math.sqrt(m)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (m * sm) * math.pi)
    dlon = (dlon * 180.0) / (_A / sm * math.cos(rad) * math.pi)
    return lat + dlat, lon + dlon


def gcj2wgs(lat, lon):
    """Convert GCJ-02 back to WGS-84 by fixed-point iteration (3 rounds)."""
    if out_of_china(lat, lon):
        return lat, lon
    wlat, wlon = lat, lon
    for _ in range(3):
        glat, glon = wgs2gcj(wlat, wlon)
        wlat -= glat - lat
        wlon -= glon - lon
    return wlat, wlon


def distance_bearing(lat0, lon0, lat1, lon1):
    """Great-circle-ish distance in km plus bearing in degrees.

    Equirectangular approximation; error stays below 0.5% within 1000 km,
    which is well inside what a single-receiver ADS-B setup can resolve.
    """
    dy = (lat1 - lat0) * 110.574
    dx = (lon1 - lon0) * 111.320 * math.cos(math.radians(lat0))
    return math.hypot(dx, dy), (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0


def merc(lat, lon, z):
    """Web Mercator: return the global pixel coordinate at zoom ``z``."""
    n = 256.0 * (2**z)
    x = (lon + 180.0) / 360.0 * n
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return x, y


def inv_merc(x, y, z):
    """Inverse Web Mercator: pixel coordinate back to latitude/longitude."""
    n = 256.0 * (2**z)
    lon = x / n * 360.0 - 180.0
    k = math.pi * (1.0 - 2.0 * y / n)
    return math.degrees(math.atan(math.sinh(k))), lon
