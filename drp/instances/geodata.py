"""Instances built from the supplied delivery coordinates (roadmap §3.2).

Until now every instance in the study was sampled uniformly at random inside a
square. `data/source/Last_Mile_Delivery_Coordinates.csv` -- 4,360 real delivery
points across the six districts of Pontianak -- sat in the repository unused by
anything the solvers ran on. This module wires it in.

What changes when the geography is real
---------------------------------------
Coordinates are ``(lat, lon)`` and the instance is built with ``geodesic=True``,
so `drp.geometry.distance.haversine_matrix` gives distances in **kilometres**
instead of the arbitrary units the synthetic generator uses. Everything
downstream -- energy, battery, the solvers, the plots -- is metric-agnostic and
needs no change; only the numbers' units do. The one real difference is
statistical: real delivery points are clustered along roads and rivers rather
than spread uniformly, which is exactly the structure a uniform sample throws
away.

Reproducibility
---------------
The source CSV is never modified. Selection is deterministic: points are sorted
into a canonical order first, then sampled with a seeded
`numpy.random.default_rng`, so a given ``(area, count, seed)`` always yields the
same instance. Demands are seeded the same way. The battery is calibrated by the
same nearest-neighbour rule the synthetic generator uses
(`drp.instances.generator.calibrate_battery`), so a geographic instance is
neither trivially loose nor infeasible.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np

from drp.core.instance import DRPInstance
from drp.geometry.nofly import Polygon, point_in_any

PathLike = Union[str, Path]

#: The dataset shipped with the project. Resolved from the package location so
#: it works whichever directory the caller runs from.
DEFAULT_DATASET = (Path(__file__).resolve().parents[2]
                   / "data" / "source" / "Last_Mile_Delivery_Coordinates.csv")

KM_PER_DEGREE_LAT = 110.574


@dataclass(frozen=True)
class DeliveryPoint:
    """One row of the source CSV."""

    district: str
    road_slot: str
    lat: float
    lon: float

    @property
    def coord(self) -> Tuple[float, float]:
        return (self.lat, self.lon)


def load_delivery_points(path: PathLike = DEFAULT_DATASET) -> List[DeliveryPoint]:
    """Read the delivery-point CSV. Rows with unreadable coordinates are skipped."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"delivery dataset not found at {p}. It ships with the repository "
            "under data/source/; pass an explicit path if it lives elsewhere.")

    points: List[DeliveryPoint] = []
    with p.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            try:
                lat = float(row["Latitude"])
                lon = float(row["Longitude"])
            except (KeyError, TypeError, ValueError):
                continue
            points.append(DeliveryPoint(district=(row.get("District") or "").strip(),
                                        road_slot=(row.get("Road_Slot") or "").strip(),
                                        lat=lat, lon=lon))
    if not points:
        raise ValueError(f"{p}: no usable rows")
    return points


def canonical_order(points: Iterable[DeliveryPoint]) -> List[DeliveryPoint]:
    """A total order on points, so sampling does not depend on file order."""
    return sorted(points, key=lambda q: (q.district, q.road_slot, q.lat, q.lon))


def filter_points(points: Sequence[DeliveryPoint],
                  district: Optional[str] = None,
                  road_slot: Optional[str] = None) -> List[DeliveryPoint]:
    """Select by district and/or road slot; matching is case-insensitive."""
    out = list(points)
    if district:
        want = district.strip().lower()
        out = [q for q in out if q.district.lower() == want]
    if road_slot:
        want = road_slot.strip().lower()
        out = [q for q in out if q.road_slot.lower() == want]
    return out


def centroid(points: Sequence[DeliveryPoint]) -> Tuple[float, float]:
    return (float(np.mean([q.lat for q in points])),
            float(np.mean([q.lon for q in points])))


def district_centroids(points: Sequence[DeliveryPoint]) -> Dict[str, Tuple[float, float]]:
    """A gazetteer of district name -> centroid, derived from the dataset itself.

    This is deliberately *not* geocoding: no network, no external service, no
    address parsing. It resolves the handful of place names the dataset already
    contains, which is what a scenario file needs to say "put the depot in
    Pontianak South" (roadmap §3.1). Real geocoding is still not done.
    """
    grouped: Dict[str, List[DeliveryPoint]] = {}
    for q in points:
        grouped.setdefault(q.district, []).append(q)
    return {name: centroid(group) for name, group in sorted(grouped.items())}


def geo_circle_polygon(lat: float, lon: float, radius_km: float,
                       sides: int = 12) -> Polygon:
    """A closed no-fly circle of `radius_km` around ``(lat, lon)``.

    Vertices are in ``(lat, lon)`` degrees to match the instance's coordinate
    space, with the longitude radius widened by ``1 / cos(lat)`` so the shape is
    a circle on the ground rather than in degree space.
    """
    dlat = radius_km / KM_PER_DEGREE_LAT
    dlon = dlat / max(math.cos(math.radians(lat)), 1e-6)
    return [(lat + dlat * math.sin(2 * math.pi * i / sides),
             lon + dlon * math.cos(2 * math.pi * i / sides))
            for i in range(sides)]


def sample_points(points: Sequence[DeliveryPoint],
                  count: int,
                  seed: int) -> List[DeliveryPoint]:
    """Deterministically pick `count` distinct points from `points`."""
    ordered = canonical_order(points)
    if count > len(ordered):
        raise ValueError(f"asked for {count} points but only {len(ordered)} "
                         "match the selection")
    rng = np.random.default_rng(seed)
    idx = sorted(rng.choice(len(ordered), size=count, replace=False).tolist())
    return [ordered[i] for i in idx]


def instance_from_points(name: str,
                         points: Sequence[DeliveryPoint],
                         n_drones: int,
                         seed: int = 1,
                         depot: Optional[Tuple[float, float]] = None,
                         demand_min: float = 0.5,
                         demand_max: float = 2.0,
                         alpha: float = 1.0,
                         beta: float = 0.3,
                         payload_factor: float = 1.7,
                         battery_factor: float = 0.9,
                         nofly_zones: Sequence[Polygon] = (),
                         payload: Optional[float] = None,
                         battery: Optional[float] = None,
                         demands: Optional[Sequence[float]] = None,
                         geodesic: bool = True) -> DRPInstance:
    """Build a geodesic `DRPInstance` from chosen delivery points.

    `depot` defaults to the centroid of the selected customers. Demands are
    drawn from ``U(demand_min, demand_max)`` with `seed` unless `demands` gives
    them outright; payload and battery are calibrated exactly as the synthetic
    generator does unless given explicitly. `geodesic` is here for the scenario
    builder's hand-placed planar points -- real dataset points are always
    ``(lat, lon)``.
    """
    from drp.instances.generator import calibrate_battery

    if not points:
        raise ValueError("no delivery points selected")

    n = len(points)
    coords = np.zeros((n + 1, 2), dtype=float)
    coords[0] = depot if depot is not None else centroid(points)
    for k, q in enumerate(points, start=1):
        coords[k] = (q.lat, q.lon)

    demand = np.zeros(n + 1, dtype=float)
    if demands is not None:
        if len(demands) != n:
            raise ValueError(f"{len(demands)} demands for {n} customers")
        demand[1:] = np.asarray(demands, dtype=float)
    else:
        demand[1:] = np.random.default_rng(seed).uniform(demand_min, demand_max,
                                                         size=n)

    if payload is None:
        payload = max(demand_max, payload_factor * demand.sum() / n_drones,
                      float(demand.max()))
    elif payload < demand.max():
        raise ValueError(f"payload {payload:g} cannot carry the heaviest "
                         f"demand {demand.max():g}")

    inst = DRPInstance(
        name=name, n_customers=n, n_drones=n_drones,
        coords=coords, demand=demand,
        battery=math.inf, payload=float(payload),
        alpha=alpha, beta=beta,
        nofly_zones=list(nofly_zones),
        geodesic=geodesic, seed=seed,
    )
    _reject_nodes_inside_zones(inst)
    inst.battery = (float(battery) if battery is not None
                    else calibrate_battery(inst, battery_factor))
    return inst


def _reject_nodes_inside_zones(inst: DRPInstance) -> None:
    """A node inside a restricted zone cannot be reached at all.

    The visibility graph would report an infinite distance to it and every
    solver would then correctly find no feasible solution -- a confusing way to
    learn that a zone was drawn over the depot. Say so directly instead.
    """
    if not inst.nofly_zones:
        return
    inside = [i for i in range(inst.N)
              if point_in_any((float(inst.coords[i][0]),
                               float(inst.coords[i][1])), inst.nofly_zones)]
    if inside:
        where = ("the depot" if inside[0] == 0 else f"customer {inside[0]}")
        raise ValueError(
            f"{inst.name}: {where} lies inside a restricted zone, so it can "
            f"never be reached ({len(inside)} node(s) affected). Move the zone "
            "or the node.")


def build_geo_instance(name: str,
                       n_customers: int,
                       n_drones: int,
                       seed: int,
                       district: Optional[str] = None,
                       road_slot: Optional[str] = None,
                       dataset: PathLike = DEFAULT_DATASET,
                       **kwargs) -> DRPInstance:
    """Sample `n_customers` real delivery points from an area and build an instance."""
    pool = filter_points(load_delivery_points(dataset), district, road_slot)
    if not pool:
        raise ValueError(f"no delivery points for district={district!r}, "
                         f"road_slot={road_slot!r}")
    return instance_from_points(name, sample_points(pool, n_customers, seed),
                                n_drones=n_drones, seed=seed, **kwargs)


#: One instance per (size, area). The sizes mirror `BENCHMARK_SPECS` exactly so
#: a geographic result can be read next to its synthetic counterpart, and the
#: areas cycle through all six districts rather than favouring one.
GEO_BENCHMARK_SPECS: Sequence[Tuple[str, int, int, int, str, str]] = [
    ("P1_n5_k2",   5,  2, 301, "Pontianak City",      "III"),
    ("P2_n6_k2",   6,  2, 302, "Pontianak North",     "III"),
    ("P3_n7_k2",   7,  3, 303, "Pontianak West",      "II"),
    ("P4_n8_k3",   8,  3, 304, "Pontianak South",     "IV"),
    ("P5_n9_k3",   9,  3, 305, "Pontianak East",      "III"),
    ("P6_n10_k3", 10,  3, 306, "Pontianak Southeast", "III"),
    ("P7_n12_k4", 12,  4, 307, "Pontianak City",      "IV"),
    ("P8_n15_k4", 15,  4, 308, "Pontianak North",     "II"),
    ("P9_n18_k5", 18,  5, 309, "Pontianak West",      "III"),
    ("P10_n20_k5", 20, 5, 310, "Pontianak South",     "II"),
    ("P11_n25_k6", 25, 6, 311, "Pontianak East",      "IV"),
    ("P12_n30_k6", 30, 6, 312, "Pontianak City",      "III"),
]


def geo_benchmark_suite(dataset: PathLike = DEFAULT_DATASET) -> List[DRPInstance]:
    """The twelve real-geography instances, sized to match the synthetic suite."""
    points = load_delivery_points(dataset)
    suite: List[DRPInstance] = []
    for name, n, k, seed, district, slot in GEO_BENCHMARK_SPECS:
        pool = filter_points(points, district, slot)
        suite.append(instance_from_points(name, sample_points(pool, n, seed),
                                          n_drones=k, seed=seed))
    return suite
