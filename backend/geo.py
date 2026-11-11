"""Geo helpers: distance, EXIF GPS extraction and complaint -> authority routing."""
import io
import math
from PIL import Image as PILImage
from models import WaterBody, Authority


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _dms(vals, ref):
    d, m, s = [float(v) for v in vals]
    deg = d + m / 60 + s / 3600
    return -deg if ref in ("S", "W") else deg


def exif_gps(raw: bytes):
    """Return (lat, lng) from a photo's EXIF block, or (None, None)."""
    try:
        gps = PILImage.open(io.BytesIO(raw)).getexif().get_ifd(0x8825)
        if gps and 2 in gps and 4 in gps:
            return _dms(gps[2], gps.get(1, "N")), _dms(gps[4], gps.get(3, "E"))
    except Exception:
        pass
    return None, None


def route_complaint(lat, lng):
    """Pick the water body + responsible (level-1) authority for a location.

    1. Nearest water body whose catchment radius contains the point.
    2. Otherwise nearest water body within 25 km (flagged as approximate).
    3. Otherwise the level-1 authority whose jurisdiction centre is closest.
    Returns (water_body | None, authority | None, note)
    """
    bodies = WaterBody.query.all()
    best, best_d = None, None
    for b in bodies:
        d = haversine_m(lat, lng, b.lat, b.lng)
        if best is None or d < best_d:
            best, best_d = b, d
    if best is not None and best_d <= (best.radius_m or 1500):
        return best, best.authority, f"Matched {best.name} ({best_d:.0f} m away)"
    if best is not None and best_d <= 25000:
        return best, best.authority, f"Nearest registered water body: {best.name} ({best_d / 1000:.1f} km)"
    locals_ = [a for a in Authority.query.filter_by(level=1).all() if a.lat is not None]
    if locals_:
        a = min(locals_, key=lambda x: haversine_m(lat, lng, x.lat, x.lng))
        return None, a, f"No registered water body nearby; routed to {a.name}"
    return None, None, "No authority available"
