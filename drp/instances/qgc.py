"""QGroundControl mission export (roadmap §3.5).

A solved route is a list of customer indices. A drone cannot fly that. This
module turns each drone's route into a QGroundControl ``.plan`` file -- the
mission format QGC, PX4 and ArduPilot ground stations load directly -- so a
solution leaves this repository as something a real ground station will open.

One plan per drone
------------------
A ``.plan`` describes *one* vehicle's mission, so a K-drone solution exports as
K files. Each is: take off at the depot, fly to every customer on the route in
order (with a hold at each stop for the drop), return to the depot, land.
Polygonal no-fly zones become **exclusion geofence polygons**, which is the
closest thing the format has to the constraint the solver actually respected.

Coordinates
-----------
A geodesic instance already carries ``(lat, lon)``, so it exports as-is. A
synthetic instance carries arbitrary planar units, and a mission file needs real
coordinates -- so a planar export requires an `anchor`: the ``(lat, lon)`` the
origin maps to, plus how many metres one coordinate unit is worth. That is a
local tangent-plane approximation, good to well under a metre over a few
kilometres and honest about being an approximation. Without an anchor a planar
export raises rather than inventing a location.

What a plan cannot carry
------------------------
Payload, battery budget and the load-dependent energy model have no
representation in the format: a ``.plan`` is a path, not a plan for a cargo
aircraft. `mission_summary` reports the numbers that were dropped, so the flight
plan and the optimisation result can be checked against each other by hand.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from drp.core.energy import route_energy, route_weight
from drp.core.instance import DRPInstance
from drp.core.solution import Solution

PathLike = Union[str, Path]

# MAVLink command ids used below.
MAV_CMD_NAV_WAYPOINT = 16
MAV_CMD_NAV_LAND = 21
MAV_CMD_NAV_TAKEOFF = 22
MAV_FRAME_GLOBAL_RELATIVE_ALT = 3

METRES_PER_DEGREE_LAT = 111_320.0


@dataclass(frozen=True)
class Anchor:
    """Where a planar instance sits on the Earth.

    ``(0, 0)`` in instance coordinates is `lat`/`lon`; one coordinate unit is
    `metres_per_unit` metres east or north. Instance coordinates are read as
    ``(x, y) = (east, north)``.
    """

    lat: float
    lon: float
    metres_per_unit: float = 100.0

    def to_latlon(self, x: float, y: float) -> Tuple[float, float]:
        dlat = (y * self.metres_per_unit) / METRES_PER_DEGREE_LAT
        cos_lat = max(math.cos(math.radians(self.lat)), 1e-6)
        dlon = (x * self.metres_per_unit) / (METRES_PER_DEGREE_LAT * cos_lat)
        return (self.lat + dlat, self.lon + dlon)


def node_latlon(inst: DRPInstance, node: int,
                anchor: Optional[Anchor] = None) -> Tuple[float, float]:
    """The ``(lat, lon)`` of an instance node, projecting planar ones."""
    x, y = float(inst.coords[node][0]), float(inst.coords[node][1])
    if inst.geodesic:
        return (x, y)          # geodesic instances store (lat, lon)
    if anchor is None:
        raise ValueError(
            f"{inst.name} is not geodesic, so its coordinates are arbitrary "
            "planar units. Pass an anchor (lat, lon, metres_per_unit) saying "
            "where the origin is before exporting a flight plan.")
    return anchor.to_latlon(x, y)


def _item(command: int, params: Sequence[Any], lat: float, lon: float,
          alt: float, seq: int) -> Dict[str, Any]:
    return {
        "AMSLAltAboveTerrain": None,
        "Altitude": alt,
        "AltitudeMode": 1,
        "autoContinue": True,
        "command": command,
        "doJumpId": seq,
        "frame": MAV_FRAME_GLOBAL_RELATIVE_ALT,
        "params": [*params, lat, lon, alt],
        "type": "SimpleItem",
    }


def route_to_qgc_plan(inst: DRPInstance,
                      route: Sequence[int],
                      anchor: Optional[Anchor] = None,
                      altitude: float = 60.0,
                      hold_seconds: float = 20.0,
                      cruise_speed: float = 15.0,
                      hover_speed: float = 5.0) -> Dict[str, Any]:
    """One drone's route as a QGroundControl ``.plan`` document."""
    if not route:
        raise ValueError("empty route: nothing to fly")

    depot = node_latlon(inst, 0, anchor)
    items: List[Dict[str, Any]] = [
        _item(MAV_CMD_NAV_TAKEOFF, [0, 0, 0, None], depot[0], depot[1],
              altitude, 1),
    ]
    for stop in route:
        lat, lon = node_latlon(inst, int(stop), anchor)
        items.append(_item(MAV_CMD_NAV_WAYPOINT, [hold_seconds, 0, 0, None],
                           lat, lon, altitude, len(items) + 1))
    items.append(_item(MAV_CMD_NAV_WAYPOINT, [0, 0, 0, None], depot[0],
                       depot[1], altitude, len(items) + 1))
    items.append(_item(MAV_CMD_NAV_LAND, [0, 0, 0, None], depot[0], depot[1],
                       0.0, len(items) + 1))

    fences = [{
        "inclusion": False,
        "version": 1,
        "polygon": [list(_polygon_vertex(inst, vertex, anchor))
                    for vertex in zone],
    } for zone in inst.nofly_zones]

    return {
        "fileType": "Plan",
        "version": 1,
        "groundStation": "QGroundControl",
        "geoFence": {"circles": [], "polygons": fences, "version": 2},
        "rallyPoints": {"points": [], "version": 2},
        "mission": {
            "version": 2,
            "firmwareType": 12,          # PX4
            "vehicleType": 2,            # multirotor
            "cruiseSpeed": cruise_speed,
            "hoverSpeed": hover_speed,
            "globalPlanAltitudeMode": 1,
            "plannedHomePosition": [depot[0], depot[1], 0.0],
            "items": items,
        },
    }


def _polygon_vertex(inst: DRPInstance, vertex: Sequence[float],
                    anchor: Optional[Anchor]) -> Tuple[float, float]:
    if inst.geodesic:
        return (float(vertex[0]), float(vertex[1]))
    if anchor is None:
        raise ValueError("planar no-fly polygon needs an anchor to export")
    return anchor.to_latlon(float(vertex[0]), float(vertex[1]))


def solution_to_qgc_plans(inst: DRPInstance,
                          sol: Solution,
                          anchor: Optional[Anchor] = None,
                          **kwargs) -> Dict[int, Dict[str, Any]]:
    """Every used drone's mission, keyed by drone index."""
    return {k: route_to_qgc_plan(inst, route, anchor, **kwargs)
            for k, route in enumerate(sol.routes) if route}


def write_qgc_plans(inst: DRPInstance,
                    sol: Solution,
                    output: PathLike,
                    anchor: Optional[Anchor] = None,
                    **kwargs) -> List[Path]:
    """Write one ``.plan`` per used drone and return the paths.

    `output` may be a directory (one file per drone inside it) or a ``.plan``
    path, which is only allowed when exactly one drone flies.
    """
    plans = solution_to_qgc_plans(inst, sol, anchor, **kwargs)
    if not plans:
        raise ValueError("solution has no non-empty route to export")

    out = Path(output)
    if out.suffix.lower() == ".plan":
        if len(plans) > 1:
            raise ValueError(
                f"{len(plans)} drones fly in this solution, and a .plan file "
                "describes one vehicle's mission. Give a directory instead and "
                "one file per drone will be written into it.")
        out.parent.mkdir(parents=True, exist_ok=True)
        (drone, plan), = plans.items()
        out.write_text(json.dumps(plan, indent=4), encoding="utf-8")
        return [out]

    out.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    stem = "".join(ch if ch.isalnum() or ch in "-_" else "_"
                   for ch in inst.name) or "mission"
    for drone, plan in plans.items():
        p = out / f"{stem}_drone{drone + 1}.plan"
        p.write_text(json.dumps(plan, indent=4), encoding="utf-8")
        written.append(p)
    return written


def mission_summary(inst: DRPInstance, sol: Solution) -> List[Dict[str, Any]]:
    """Per-drone figures the ``.plan`` format cannot carry.

    Exists so an exported mission can be reconciled against the optimisation
    result by hand: the plan file says where to fly, this says what the solver
    believed about the flight.
    """
    rows = []
    for k, route in enumerate(sol.routes):
        if not route:
            continue
        rows.append({
            "drone": k,
            "stops": len(route),
            "payload_at_departure": float(route_weight(inst, route)),
            "payload_limit": float(inst.payload),
            "energy": float(route_energy(inst, route)),
            "battery_limit": (None if math.isinf(inst.battery)
                              else float(inst.battery)),
            "units": "km" if inst.geodesic else "instance units",
        })
    return rows
