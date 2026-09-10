"""Turning an OSM extract into a basemap the replay page can draw (roadmap §3.4).

`drp.geometry.osm` reads the extract; this decides what survives into the page.
Those are different jobs. A 209 MB extract of Pontianak yields ~14,000 road
polylines, and shipping all of them inside a self-contained HTML file would make
a page nobody can open to show a twenty-stop delivery round.

So this clips to the instance's own neighbourhood, thins each polyline with
Douglas-Peucker, rounds coordinates to about a metre, and drops residential
streets first when the result is still too big. The output is
``drp-basemap/v1``: a few hundred kilobytes of real geography, in the same
``(lat, lon)`` order the instances use.

What is deliberately absent
---------------------------
Buildings. The extract has 193,831 of them and the land-use polygons already say
where the built-up areas are. Also labels beyond named settlements: street names
would need collision handling at every zoom, which the page's existing label
logic does for districts and would have to be rebuilt for thousands.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from drp.core.instance import DRPInstance
from drp.geometry.osm import (BBox, LatLon, OSMData, bbox_around, clip_to_bbox,
                              read_osm)
from drp.instances.geodata import KM_PER_DEGREE_LAT

PathLike = Union[str, Path]

BASEMAP_SCHEMA = "drp-basemap/v1"

#: Roughly a metre at the equator; finer than any screen will show.
COORD_DECIMALS = 5


def _perpendicular_distance(p: LatLon, a: LatLon, b: LatLon,
                            lon_scale: float) -> float:
    """Point-to-segment distance in degree space, longitudes rescaled."""
    ax, ay = a[1] * lon_scale, a[0]
    bx, by = b[1] * lon_scale, b[0]
    px, py = p[1] * lon_scale, p[0]
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def simplify(line: Sequence[LatLon], epsilon_deg: float,
             lon_scale: float = 1.0) -> List[LatLon]:
    """Douglas-Peucker, iterative so a long coastline cannot blow the stack."""
    if len(line) < 3 or epsilon_deg <= 0:
        return list(line)

    keep = [False] * len(line)
    keep[0] = keep[-1] = True
    stack = [(0, len(line) - 1)]
    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        worst, worst_at = 0.0, first
        for i in range(first + 1, last):
            d = _perpendicular_distance(line[i], line[first], line[last],
                                        lon_scale)
            if d > worst:
                worst, worst_at = d, i
        if worst > epsilon_deg:
            keep[worst_at] = True
            stack.append((first, worst_at))
            stack.append((worst_at, last))
    return [p for p, k in zip(line, keep) if k]


def _round(line: Sequence[LatLon]) -> List[List[float]]:
    out: List[List[float]] = []
    for lat, lon in line:
        point = [round(lat, COORD_DECIMALS), round(lon, COORD_DECIMALS)]
        if not out or point != out[-1]:      # drop duplicates rounding created
            out.append(point)
    return out


def _prepare(lines: Sequence[Sequence[LatLon]], bbox: BBox,
             epsilon_deg: float, lon_scale: float) -> List[List[List[float]]]:
    prepared = []
    for line in clip_to_bbox(lines, bbox):
        thinned = _round(simplify(line, epsilon_deg, lon_scale))
        if len(thinned) >= 2:
            prepared.append(thinned)
    return prepared


def build_basemap(osm: OSMData,
                  bbox: BBox,
                  simplify_m: float = 6.0,
                  max_street_lines: Optional[int] = 2500) -> Dict[str, Any]:
    """Clip, thin and package an extract for one instance's neighbourhood.

    `simplify_m` is the Douglas-Peucker tolerance in metres -- six is well below
    one screen pixel at the zooms the page uses, so the thinning is invisible.
    `max_street_lines` caps the residential layer only; arterials, water and
    land use are always kept in full, because they are what makes a map
    readable when it is zoomed out.
    """
    epsilon_deg = (simplify_m / 1000.0) / KM_PER_DEGREE_LAT
    mid_lat = math.radians((bbox[0] + bbox[2]) / 2.0)
    lon_scale = max(math.cos(mid_lat), 1e-6)

    roads: Dict[str, List[List[List[float]]]] = {}
    for cls in ("arterial", "secondary", "street"):
        lines = [line for c, line in osm.roads if c == cls]
        prepared = _prepare(lines, bbox, epsilon_deg, lon_scale)
        if cls == "street" and max_street_lines is not None:
            # Longest first: the streets that carry the shape of the place.
            prepared.sort(key=len, reverse=True)
            prepared = prepared[:max_street_lines]
        roads[cls] = prepared

    places = [{"name": p.name, "kind": p.kind,
               "lat": round(p.lat, COORD_DECIMALS),
               "lon": round(p.lon, COORD_DECIMALS)}
              for p in osm.places
              if bbox[0] <= p.lat <= bbox[2] and bbox[1] <= p.lon <= bbox[3]]

    return {
        "schema": BASEMAP_SCHEMA,
        "bounds": [round(v, 6) for v in bbox],
        "roads": roads,
        "water": {
            "lines": _prepare(osm.waterways, bbox, epsilon_deg, lon_scale),
            "areas": _prepare(osm.water_areas, bbox, epsilon_deg, lon_scale),
        },
        "green": _prepare(osm.green, bbox, epsilon_deg, lon_scale),
        "built": _prepare(osm.built, bbox, epsilon_deg, lon_scale),
        "places": places,
    }


def basemap_for_instance(inst: DRPInstance,
                         osm: Union[OSMData, PathLike],
                         margin_km: Optional[float] = None,
                         **kwargs) -> Dict[str, Any]:
    """The basemap covering an instance's stops, with a margin around them.

    The margin defaults to a third of the instance's own span, because the page
    does not frame the stops exactly: it pads them by 14% and then widens to the
    map panel's aspect ratio. A fixed small margin leaves the streets stopping
    in mid-air part way across the frame -- which is what a first render did,
    with a visible edge down the east side of the city.

    Raises for a planar instance: its coordinates are arbitrary units with no
    position on Earth, so there is no honest way to line a map up with them.
    """
    if not inst.geodesic:
        raise ValueError(
            f"{inst.name} is not geodesic, so it has no location on Earth to "
            "draw a map of. Build it from the delivery dataset (drp build) or "
            "keep the synthetic basemap.")
    data = osm if isinstance(osm, OSMData) else read_osm(osm)
    points: List[LatLon] = [(float(c[0]), float(c[1])) for c in inst.coords]
    for zone in inst.nofly_zones:
        points.extend((float(v[0]), float(v[1])) for v in zone)

    if margin_km is None:
        lat_span = (max(p[0] for p in points) - min(p[0] for p in points))
        lon_span = (max(p[1] for p in points) - min(p[1] for p in points))
        mid = math.radians(sum(p[0] for p in points) / len(points))
        span_km = max(lat_span, lon_span * math.cos(mid)) * KM_PER_DEGREE_LAT
        margin_km = max(0.6, span_km / 3.0)
    return build_basemap(data, bbox_around(points, margin_km), **kwargs)


def write_basemap(basemap: Dict[str, Any], path: PathLike) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(basemap, separators=(",", ":")), encoding="utf-8")
    return p


def load_basemap(path: PathLike) -> Dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    schema = data.get("schema")
    if schema != BASEMAP_SCHEMA:
        raise ValueError(f"unsupported basemap schema {schema!r}; "
                         f"expected {BASEMAP_SCHEMA!r}")
    return data


def basemap_stats(basemap: Dict[str, Any]) -> Dict[str, int]:
    """Line and vertex counts per layer -- what governs the page's weight."""
    def vertices(lines: Sequence[Sequence[Any]]) -> int:
        return sum(len(line) for line in lines)

    roads = basemap.get("roads", {})
    return {
        "arterial": len(roads.get("arterial", [])),
        "secondary": len(roads.get("secondary", [])),
        "street": len(roads.get("street", [])),
        "water_lines": len(basemap.get("water", {}).get("lines", [])),
        "water_areas": len(basemap.get("water", {}).get("areas", [])),
        "green": len(basemap.get("green", [])),
        "built": len(basemap.get("built", [])),
        "places": len(basemap.get("places", [])),
        "vertices": sum(vertices(v) for v in roads.values())
                    + vertices(basemap.get("water", {}).get("lines", []))
                    + vertices(basemap.get("water", {}).get("areas", []))
                    + vertices(basemap.get("green", []))
                    + vertices(basemap.get("built", [])),
    }
