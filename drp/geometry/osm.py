"""Reading an OpenStreetMap extract (roadmap §3.4).

The web replay has always drawn its own city: a seeded, synthetic river with
synthetic arterials and land-use blobs. It is honest about being invented, and
it looks plausible, but every street on it is a lie. With an OSM extract of the
same coordinates the instances actually use, it does not have to be.

This module reads an ``.osm`` XML extract with nothing but the standard library
-- no `osmium`, no `protobuf`, which is why the fetch instructions ask for XML
rather than `.pbf`. It streams with `iterparse` and keeps only what a basemap
needs, so a 209 MB extract of Pontianak parses in about 20 seconds and yields a
few hundred kilobytes of geometry.

Two passes, deliberately
------------------------
Pass one reads the ways and records which node ids they reference; pass two
reads the nodes and keeps only those. Holding every node's coordinates instead
would be one pass and several hundred megabytes of dictionary, on a file whose
whole point is that it is bigger than what we want out of it.

Coordinates come out as ``(lat, lon)`` -- the same order `DRPInstance` uses when
``geodesic=True``, so nothing needs flipping downstream.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

PathLike = Union[str, Path]
LatLon = Tuple[float, float]
BBox = Tuple[float, float, float, float]     # (min_lat, min_lon, max_lat, max_lon)

#: How OSM's ``highway`` values map onto the three weights a chart needs.
ROAD_CLASSES: Dict[str, str] = {
    "motorway": "arterial", "motorway_link": "arterial",
    "trunk": "arterial", "trunk_link": "arterial",
    "primary": "arterial", "primary_link": "arterial",
    "secondary": "secondary", "secondary_link": "secondary",
    "tertiary": "secondary", "tertiary_link": "secondary",
    "residential": "street", "living_street": "street",
    "unclassified": "street",
}

WATER_WAYS = {"river", "canal", "stream"}
WATER_AREAS = {"water", "wetland"}
GREEN_LANDUSE = {"forest", "grass", "meadow", "farmland", "orchard",
                 "recreation_ground", "village_green", "cemetery"}
BUILT_LANDUSE = {"residential", "commercial", "industrial", "retail",
                 "construction"}
PLACE_KINDS = {"city", "town", "suburb", "village", "neighbourhood", "quarter",
               "hamlet"}


@dataclass
class Place:
    """A named point: the raw material of an offline gazetteer."""

    name: str
    kind: str
    lat: float
    lon: float


@dataclass
class OSMData:
    """Everything kept from an extract, already resolved to coordinates."""

    roads: List[Tuple[str, List[LatLon]]] = field(default_factory=list)
    waterways: List[List[LatLon]] = field(default_factory=list)
    water_areas: List[List[LatLon]] = field(default_factory=list)
    green: List[List[LatLon]] = field(default_factory=list)
    built: List[List[LatLon]] = field(default_factory=list)
    places: List[Place] = field(default_factory=list)
    bounds: Optional[BBox] = None

    def summary(self) -> str:
        return (f"{len(self.roads)} roads, {len(self.waterways)} waterways, "
                f"{len(self.water_areas)} water areas, {len(self.green)} green "
                f"areas, {len(self.built)} built-up areas, "
                f"{len(self.places)} named places")


def _tags(element: ET.Element) -> Dict[str, str]:
    return {t.get("k", ""): t.get("v", "") for t in element.findall("tag")}


def _classify(tags: Dict[str, str], keep_streets: bool) -> Optional[str]:
    """Which bucket a way belongs in, or None to discard it.

    Buildings are discarded outright: the Pontianak extract holds 193,831 of
    them, which is two orders of magnitude more geometry than a city-scale
    basemap can draw and more than the land-use polygons already convey.
    """
    if "highway" in tags:
        cls = ROAD_CLASSES.get(tags["highway"])
        if cls is None or (cls == "street" and not keep_streets):
            return None
        return f"road:{cls}"
    if tags.get("waterway") in WATER_WAYS:
        return "waterway"
    if tags.get("natural") in WATER_AREAS or tags.get("water"):
        return "water_area"
    if tags.get("landuse") in GREEN_LANDUSE or tags.get("leisure") == "park":
        return "green"
    if tags.get("landuse") in BUILT_LANDUSE:
        return "built"
    return None


def read_osm(path: PathLike, keep_streets: bool = True) -> OSMData:
    """Parse an OSM XML extract into the handful of layers a basemap draws."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"no OSM extract at {p}. Fetch one for the area you need, e.g. "
            "https://overpass-api.de/api/map?bbox=<west>,<south>,<east>,<north>"
            " -- XML, not .pbf.")

    wanted: Dict[int, Tuple[str, List[int]]] = {}
    needed: Set[int] = set()
    data = OSMData()

    # Pass 1: the ways worth keeping, and the node ids they need.
    for _event, el in ET.iterparse(p, events=("end",)):
        if el.tag == "way":
            kind = _classify(_tags(el), keep_streets)
            if kind is not None:
                refs = [int(nd.get("ref", 0)) for nd in el.findall("nd")]
                if len(refs) >= 2:
                    wanted[int(el.get("id", 0))] = (kind, refs)
                    needed.update(refs)
            el.clear()
        elif el.tag == "node":
            tags = _tags(el)
            kind, name = tags.get("place"), tags.get("name")
            if name and kind in PLACE_KINDS:
                data.places.append(Place(name=name, kind=kind,
                                         lat=float(el.get("lat", "nan")),
                                         lon=float(el.get("lon", "nan"))))
            el.clear()
        elif el.tag == "bounds":
            data.bounds = (float(el.get("minlat", "nan")),
                           float(el.get("minlon", "nan")),
                           float(el.get("maxlat", "nan")),
                           float(el.get("maxlon", "nan")))
            el.clear()
        elif el.tag == "relation":
            el.clear()

    # Pass 2: coordinates, for those node ids only.
    coords: Dict[int, LatLon] = {}
    for _event, el in ET.iterparse(p, events=("end",)):
        if el.tag == "node":
            nid = int(el.get("id", 0))
            if nid in needed:
                coords[nid] = (float(el.get("lat", "nan")),
                               float(el.get("lon", "nan")))
            el.clear()
        elif el.tag in ("way", "relation"):
            el.clear()         # no early exit: do not assume nodes precede ways

    for kind, refs in wanted.values():
        line = [coords[r] for r in refs if r in coords]
        if len(line) < 2:
            continue
        if kind.startswith("road:"):
            data.roads.append((kind.split(":", 1)[1], line))
        elif kind == "waterway":
            data.waterways.append(line)
        elif kind == "water_area":
            data.water_areas.append(line)
        elif kind == "green":
            data.green.append(line)
        elif kind == "built":
            data.built.append(line)
    return data


def place_gazetteer(data: OSMData) -> Dict[str, LatLon]:
    """Name -> coordinate, largest place winning when a name repeats.

    This is real geocoding, just offline and small: the names come from the
    extract, not from a service, and resolving one needs no network. It only
    knows settlements -- `drp.instances.geodata.district_centroids` still
    handles the dataset's own district names, and street addresses are not
    handled at all.
    """
    rank = {kind: i for i, kind in enumerate(
        ["city", "town", "suburb", "quarter", "neighbourhood", "village",
         "hamlet"])}
    best: Dict[str, Tuple[int, LatLon]] = {}
    for place in data.places:
        score = rank.get(place.kind, 99)
        key = place.name.strip().lower()
        if key not in best or score < best[key][0]:
            best[key] = (score, (place.lat, place.lon))
    return {name: coord for name, (_score, coord) in best.items()}


def bbox_around(points: Sequence[LatLon], margin_km: float = 1.0) -> BBox:
    """A bounding box covering `points` with a margin, in degrees."""
    from drp.instances.geodata import KM_PER_DEGREE_LAT
    import math

    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    dlat = margin_km / KM_PER_DEGREE_LAT
    mid = math.radians(sum(lats) / len(lats))
    dlon = dlat / max(math.cos(mid), 1e-6)
    return (min(lats) - dlat, min(lons) - dlon,
            max(lats) + dlat, max(lons) + dlon)


def clip_to_bbox(lines: Iterable[Sequence[LatLon]],
                 bbox: BBox) -> List[List[LatLon]]:
    """Keep every line with a point inside `bbox`, whole.

    Deliberately not a true polygon clip: a road cut exactly at the frame edge
    looks worse than one running a little past it, and the page draws inside a
    viewport anyway.
    """
    min_lat, min_lon, max_lat, max_lon = bbox
    kept = []
    for line in lines:
        if any(min_lat <= lat <= max_lat and min_lon <= lon <= max_lon
               for lat, lon in line):
            kept.append(list(line))
    return kept
