"""The scenario builder (roadmap §3.1).

An instance is a *result*: coordinates, demands, a calibrated battery. A
scenario is the *recipe* that produced it -- "twenty stops in Pontianak South,
five drones, a restricted circle over the airport" -- and it is the thing a
person actually wants to edit. This module defines that recipe as a small
declarative JSON format, ``drp-scenario/v1``, and builds a `DRPInstance` from
it.

A scenario file is short enough to write by hand::

    {
      "schema": "drp-scenario/v1",
      "name": "pontianak-south-20",
      "seed": 7,
      "source": {"district": "Pontianak South", "road_slot": "IV", "count": 20},
      "depot": {"place": "Pontianak South"},
      "fleet": {"n_drones": 5},
      "nofly": {"circles": [{"centre": {"place": "Pontianak City"},
                             "radius_km": 0.8}]}
    }

``drp build scenario.json -o inst.json`` turns it into a normal
``drp-instance/v1`` file that every other command already understands. Nothing
downstream learns about scenarios.

Three kinds of source
---------------------
``{"district": ..., "road_slot": ..., "count": n}``
    Sample real delivery points from the shipped dataset (§3.2).
``{"points": [{"coord": [x, y], "demand": 1.4}, ...]}``
    Coordinates given outright, for a hand-built what-if.
``{"synthetic": {"n": 12, "zones": 2}}``
    Fall through to the original generator, so the synthetic suite stays
    reachable from the same file format.

Place names resolve against the dataset's own district centroids
(`drp.instances.geodata.district_centroids`). That is a gazetteer lookup, not
geocoding: it needs no network and only knows names the dataset contains.
Address-level geocoding and OSM basemaps remain not done.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from drp.core.instance import DRPInstance
from drp.geometry.nofly import Polygon, circle_polygon
from drp.instances.geodata import (DEFAULT_DATASET, DeliveryPoint,
                                   district_centroids, filter_points,
                                   geo_circle_polygon, instance_from_points,
                                   load_delivery_points, sample_points)

SCENARIO_SCHEMA = "drp-scenario/v1"

PathLike = Union[str, Path]

_TOP_KEYS = {"schema", "name", "seed", "source", "depot", "fleet", "energy",
             "demand", "nofly", "geodesic", "notes"}
_SOURCE_KEYS = {"dataset", "district", "road_slot", "count", "points",
                "synthetic"}


def scenario_template() -> Dict[str, Any]:
    """A filled-in example, for ``drp build --example``."""
    return {
        "schema": SCENARIO_SCHEMA,
        "name": "pontianak-south-20",
        "seed": 7,
        "source": {"district": "Pontianak South", "road_slot": "IV",
                   "count": 20},
        "depot": {"place": "Pontianak South"},
        "fleet": {"n_drones": 5, "battery": {"factor": 0.9}},
        "energy": {"alpha": 1.0, "beta": 0.3},
        "demand": {"min": 0.5, "max": 2.0},
        "nofly": {"circles": [{"centre": {"place": "Pontianak City"},
                               "radius_km": 0.8}]},
        "notes": "Twenty real delivery points, one restricted circle downtown.",
    }


def load_scenario(path: PathLike) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_scenario(spec: Dict[str, Any], path: PathLike) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return p


def build_scenario(spec: Dict[str, Any],
                   dataset: Optional[PathLike] = None) -> DRPInstance:
    """Turn a ``drp-scenario/v1`` mapping into an instance.

    `dataset` overrides the CSV path for dataset-backed scenarios; the file's
    own ``source.dataset`` wins over the shipped default when neither is given.
    """
    schema = spec.get("schema")
    if schema is not None and schema != SCENARIO_SCHEMA:
        raise ValueError(f"unsupported scenario schema {schema!r}; "
                         f"expected {SCENARIO_SCHEMA!r}")
    _reject_unknown(spec, _TOP_KEYS, "scenario")

    name = spec.get("name", "scenario")
    seed = int(spec.get("seed", 1))
    source = spec.get("source", {})
    _reject_unknown(source, _SOURCE_KEYS, "scenario.source")

    if "synthetic" in source:
        return _build_synthetic(name, seed, spec, source["synthetic"])

    fleet = spec.get("fleet", {})
    energy = spec.get("energy", {})
    demand_spec = spec.get("demand", {})

    if "points" in source:
        points, demands = _explicit_points(source["points"])
        geodesic = bool(spec.get("geodesic", False))
    else:
        path = dataset or source.get("dataset") or DEFAULT_DATASET
        pool = filter_points(load_delivery_points(path),
                             source.get("district"), source.get("road_slot"))
        if not pool:
            raise ValueError(
                f"scenario {name!r}: no delivery points for "
                f"district={source.get('district')!r}, "
                f"road_slot={source.get('road_slot')!r}")
        count = int(source.get("count", len(pool)))
        points = sample_points(pool, count, seed)
        demands = None
        geodesic = bool(spec.get("geodesic", True))

    gazetteer = _gazetteer(source, dataset) if _needs_places(spec) else {}
    depot = _resolve_depot(spec.get("depot"), points, gazetteer)
    n_drones = int(fleet.get("n_drones", max(1, math.ceil(len(points) / 6))))
    zones = _build_zones(spec.get("nofly", {}), gazetteer, geodesic)

    payload, battery, battery_factor = _fleet_limits(fleet)

    return instance_from_points(
        name, points, n_drones=n_drones, seed=seed, depot=depot,
        demand_min=float(demand_spec.get("min", 0.5)),
        demand_max=float(demand_spec.get("max", 2.0)),
        alpha=float(energy.get("alpha", 1.0)),
        beta=float(energy.get("beta", 0.3)),
        battery_factor=battery_factor,
        nofly_zones=zones, payload=payload, battery=battery,
        demands=demands, geodesic=geodesic,
    )


def build_scenario_file(path: PathLike,
                        dataset: Optional[PathLike] = None) -> DRPInstance:
    return build_scenario(load_scenario(path), dataset=dataset)


# ---------------------------------------------------------------------------
def _reject_unknown(mapping: Dict[str, Any], allowed: set, where: str) -> None:
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise ValueError(f"{where}: unknown key(s) {', '.join(unknown)}; "
                         f"expected one of {', '.join(sorted(allowed))}")


def _explicit_points(entries: Sequence[Dict[str, Any]]
                     ) -> Tuple[List[DeliveryPoint], Optional[np.ndarray]]:
    points: List[DeliveryPoint] = []
    demands: List[Optional[float]] = []
    for entry in entries:
        coord = entry["coord"] if isinstance(entry, dict) else entry
        points.append(DeliveryPoint(district=str(entry.get("district", ""))
                                    if isinstance(entry, dict) else "",
                                    road_slot="", lat=float(coord[0]),
                                    lon=float(coord[1])))
        demands.append(float(entry["demand"])
                       if isinstance(entry, dict) and "demand" in entry else None)
    if not points:
        raise ValueError("scenario.source.points is empty")
    if any(d is None for d in demands):
        return points, None
    return points, np.array(demands, dtype=float)


def _needs_places(spec: Dict[str, Any]) -> bool:
    if isinstance(spec.get("depot"), dict) and "place" in spec["depot"]:
        return True
    for circle in spec.get("nofly", {}).get("circles", []):
        if isinstance(circle.get("centre"), dict):
            return True
    return False


def _gazetteer(source: Dict[str, Any],
               dataset: Optional[PathLike]) -> Dict[str, Tuple[float, float]]:
    path = dataset or source.get("dataset") or DEFAULT_DATASET
    return district_centroids(load_delivery_points(path))


def _resolve_place(where: Any,
                   gazetteer: Dict[str, Tuple[float, float]]
                   ) -> Tuple[float, float]:
    if isinstance(where, dict) and "place" in where:
        key = str(where["place"]).strip().lower()
        for name, coord in gazetteer.items():
            if name.strip().lower() == key:
                return coord
        raise ValueError(f"unknown place {where['place']!r}; the dataset knows "
                         f"{', '.join(sorted(gazetteer)) or '(nothing)'}")
    if isinstance(where, dict) and "coord" in where:
        return (float(where["coord"][0]), float(where["coord"][1]))
    return (float(where[0]), float(where[1]))


def _resolve_depot(depot: Any,
                   points: Sequence[DeliveryPoint],
                   gazetteer: Dict[str, Tuple[float, float]]
                   ) -> Optional[Tuple[float, float]]:
    if depot is None:
        return None
    if isinstance(depot, dict) and depot.get("centroid"):
        return None            # instance_from_points already centroids
    return _resolve_place(depot, gazetteer)


def _fleet_limits(fleet: Dict[str, Any]
                  ) -> Tuple[Optional[float], Optional[float], float]:
    """Return ``(payload, battery, battery_factor)`` from the fleet block.

    ``"battery": 30`` is an explicit budget, ``{"factor": 0.9}`` calibrates it
    from the instance, ``null`` means unbounded, and an absent key calibrates
    with the default factor.
    """
    payload = fleet.get("payload")
    payload = float(payload) if payload is not None else None

    battery_factor = 0.9
    if "battery" not in fleet:
        return payload, None, battery_factor

    battery = fleet["battery"]
    if battery is None:
        return payload, math.inf, battery_factor
    if isinstance(battery, dict):
        return payload, None, float(battery.get("factor", battery_factor))
    return payload, float(battery), battery_factor


def _build_zones(nofly: Dict[str, Any],
                 gazetteer: Dict[str, Tuple[float, float]],
                 geodesic: bool) -> List[Polygon]:
    zones: List[Polygon] = []
    for circle in nofly.get("circles", []):
        centre = _resolve_place(circle.get("centre", circle.get("center")),
                                gazetteer)
        if geodesic:
            radius = float(circle.get("radius_km", circle.get("radius", 1.0)))
            zones.append(geo_circle_polygon(centre[0], centre[1], radius,
                                            sides=int(circle.get("sides", 12))))
        else:
            radius = float(circle.get("radius", circle.get("radius_km", 1.0)))
            zones.append(circle_polygon(centre[0], centre[1], radius,
                                        sides=int(circle.get("sides", 12))))
    for poly in nofly.get("polygons", []):
        zones.append([(float(x), float(y)) for x, y in poly])
    return zones


def _build_synthetic(name: str, seed: int, spec: Dict[str, Any],
                     synthetic: Dict[str, Any]) -> DRPInstance:
    from drp.instances.generator import generate_instance, generate_zone_instance

    fleet = spec.get("fleet", {})
    energy = spec.get("energy", {})
    n = int(synthetic["n"])
    k = int(fleet.get("n_drones", synthetic.get("drones", max(1, n // 6))))
    common = dict(alpha=float(energy.get("alpha", 1.0)),
                  beta=float(energy.get("beta", 0.3)),
                  area=float(synthetic.get("area", 100.0)))
    zones = int(synthetic.get("zones", 0))
    if zones > 0:
        return generate_zone_instance(name, n, k, seed, n_zones=zones,
                                      zone_radius=float(
                                          synthetic.get("zone_radius", 12.0)),
                                      **common)
    return generate_instance(name, n, k, seed,
                             nofly_fraction=float(synthetic.get("nofly", 0.0)),
                             **common)
