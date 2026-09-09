"""Reading and writing instances and solutions (roadmap §1.2).

Two documented formats, both plain JSON:

``drp-instance/v1``
    Everything needed to reproduce a problem: depot and customers, demands,
    fleet spec, energy parameters, and no-fly geometry (edges and/or polygons).

``drp-solution/v1``
    A claimed answer plus enough evidence to check it without re-solving: the
    routes, per-leg energy and onboard weight, and a feasibility certificate.

Both carry a ``schema`` field so a reader can tell what it is holding, and both
have a JSON Schema under ``drp/instances/schema/`` for validation.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Optional, Union

import numpy as np

from drp.core.energy import route_energy, route_energy_trace, route_weight
from drp.core.feasibility import feasibility_certificate
from drp.core.instance import DRPInstance
from drp.core.solution import Solution

INSTANCE_SCHEMA = "drp-instance/v1"
SOLUTION_SCHEMA = "drp-solution/v1"

PathLike = Union[str, Path]


# ---------------------------------------------------------------------------
# Instances
# ---------------------------------------------------------------------------
def instance_to_dict(inst: DRPInstance) -> Dict[str, Any]:
    return {
        "schema": INSTANCE_SCHEMA,
        "name": inst.name,
        "n_customers": inst.n_customers,
        "fleet": {
            "n_drones": inst.n_drones,
            "payload": float(inst.payload),
            "battery": (None if math.isinf(inst.battery) else float(inst.battery)),
        },
        "energy": {"alpha": float(inst.alpha), "beta": float(inst.beta)},
        "geodesic": bool(inst.geodesic),
        "depot": [float(x) for x in inst.coords[0]],
        "customers": [
            {"id": i,
             "coord": [float(x) for x in inst.coords[i]],
             "demand": float(inst.demand[i])}
            for i in range(1, inst.N)
        ],
        "nofly": {
            "edges": sorted([int(a), int(b)] for a, b in inst.nofly_edges),
            "polygons": [[[float(x), float(y)] for x, y in poly]
                         for poly in inst.nofly_zones],
        },
        "seed": inst.seed,
    }


def instance_from_dict(d: Dict[str, Any]) -> DRPInstance:
    schema = d.get("schema")
    if schema is not None and schema != INSTANCE_SCHEMA:
        raise ValueError(f"unsupported instance schema {schema!r}; "
                         f"expected {INSTANCE_SCHEMA!r}")

    customers = d["customers"]
    n = len(customers)
    coords = np.zeros((n + 1, 2), dtype=float)
    demand = np.zeros(n + 1, dtype=float)
    coords[0] = d["depot"]
    for k, c in enumerate(customers, start=1):
        coords[k] = c["coord"]
        demand[k] = c["demand"]

    fleet = d["fleet"]
    battery = fleet.get("battery")
    energy = d.get("energy", {})
    nofly = d.get("nofly", {})

    return DRPInstance(
        name=d.get("name", "unnamed"),
        n_customers=n,
        n_drones=int(fleet["n_drones"]),
        coords=coords,
        demand=demand,
        battery=(math.inf if battery is None else float(battery)),
        payload=float(fleet["payload"]),
        alpha=float(energy.get("alpha", 1.0)),
        beta=float(energy.get("beta", 0.3)),
        nofly_edges={(int(a), int(b)) for a, b in nofly.get("edges", [])},
        nofly_zones=[[(float(x), float(y)) for x, y in poly]
                     for poly in nofly.get("polygons", [])],
        geodesic=bool(d.get("geodesic", False)),
        seed=d.get("seed"),
    )


def save_instance(inst: DRPInstance, path: PathLike) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(instance_to_dict(inst), indent=2), encoding="utf-8")
    return p


def load_instance(path: PathLike) -> DRPInstance:
    return instance_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# Solutions
# ---------------------------------------------------------------------------
def solution_to_dict(inst: DRPInstance,
                     sol: Solution,
                     method: Optional[str] = None,
                     meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    routes = []
    for k, r in enumerate(sol.routes):
        if not r:
            continue
        e = route_energy(inst, r)
        routes.append({
            "drone": k,
            "customers": [int(c) for c in r],
            "energy": (None if math.isinf(e) else float(e)),
            "payload": float(route_weight(inst, r)),
            "legs": route_energy_trace(inst, r),
        })
    return {
        "schema": SOLUTION_SCHEMA,
        "instance": inst.name,
        "method": method,
        "routes": routes,
        "certificate": feasibility_certificate(inst, sol),
        "meta": meta or {},
    }


def solution_from_dict(d: Dict[str, Any], n_drones: Optional[int] = None) -> Solution:
    schema = d.get("schema")
    if schema is not None and schema != SOLUTION_SCHEMA:
        raise ValueError(f"unsupported solution schema {schema!r}; "
                         f"expected {SOLUTION_SCHEMA!r}")
    entries = d["routes"]
    size = n_drones if n_drones is not None else len(entries)
    routes: list[list[int]] = [[] for _ in range(max(size, len(entries)))]
    for k, r in enumerate(entries):
        idx = r.get("drone", k)
        while idx >= len(routes):
            routes.append([])
        routes[idx] = [int(c) for c in r["customers"]]
    return Solution(routes)


def save_solution(inst: DRPInstance,
                  sol: Solution,
                  path: PathLike,
                  method: Optional[str] = None,
                  meta: Optional[Dict[str, Any]] = None) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(solution_to_dict(inst, sol, method, meta), indent=2),
                 encoding="utf-8")
    return p


def load_solution(path: PathLike, n_drones: Optional[int] = None) -> Solution:
    return solution_from_dict(json.loads(Path(path).read_text(encoding="utf-8")),
                              n_drones=n_drones)


# ---------------------------------------------------------------------------
# Interop exports
# ---------------------------------------------------------------------------
def solution_to_geojson(inst: DRPInstance, sol: Solution) -> Dict[str, Any]:
    """GeoJSON FeatureCollection: one LineString per drone, plus point features."""
    features = []
    for k, r in enumerate(sol.routes):
        if not r:
            continue
        pts = [0] + list(r) + [0]
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[float(inst.coords[p][0]), float(inst.coords[p][1])]
                                for p in pts],
            },
            "properties": {"drone": k,
                           "energy": float(route_energy(inst, r)),
                           "payload": float(route_weight(inst, r))},
        })
    features.append({
        "type": "Feature",
        "geometry": {"type": "Point",
                     "coordinates": [float(inst.coords[0][0]),
                                     float(inst.coords[0][1])]},
        "properties": {"role": "depot"},
    })
    for i in range(1, inst.N):
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point",
                         "coordinates": [float(inst.coords[i][0]),
                                         float(inst.coords[i][1])]},
            "properties": {"role": "customer", "id": i,
                           "demand": float(inst.demand[i])},
        })
    return {"type": "FeatureCollection", "features": features}


def solution_to_csv(inst: DRPInstance, sol: Solution) -> str:
    """A flat per-leg manifest: one row per flown leg."""
    lines = ["drone,leg,from_node,to_node,distance,onboard_weight,energy"]
    for k, r in enumerate(sol.routes):
        if not r:
            continue
        for li, leg in enumerate(route_energy_trace(inst, r)):
            lines.append(f"{k},{li},{leg['from']},{leg['to']},"
                         f"{leg['distance']:.6f},{leg['onboard']:.6f},"
                         f"{leg['energy']:.6f}")
    return "\n".join(lines) + "\n"
