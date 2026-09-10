"""Data payload for the interactive GSAP flight-playback page (roadmap §2.2).

Python's only job here is to produce JSON; every animation, easing curve and
camera move lives in `drp/viz/web/playback_template.html` instead. That split
matters beyond this one view: the search-visualisation work planned for later
(§2.4) will follow the same "Python emits a trace, JS choreographs it" pattern,
so the conventions established here -- one dict in, one self-contained HTML file
out -- are meant to be reused, not one-off.

Nothing here computes geometry itself. The flown path (including any detour
around a polygonal no-fly zone) comes from `drp.viz.static.route_polyline`, the
same helper the static PNG and the matplotlib GIF already use, so all three
views agree on what a drone actually flies. The energy and per-leg numbers come
from `drp.core.energy` and the existing `drp-instance/v1` / `drp-solution/v1`
serialisers in `drp.instances.io`, so this is an *annex* to those formats, not a
competing one.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from drp.core.energy import route_energy, route_weight
from drp.core.instance import DRPInstance
from drp.core.solution import Solution
from drp.geometry.distance import KM_PER_DEGREE
from drp.instances.io import instance_to_dict, solution_to_dict
from drp.viz.static import route_polyline
from drp.viz.theme import Theme, resolve


def projection(inst: DRPInstance) -> Optional[Dict[str, float]]:
    """How the page turns instance coordinates into the world it draws.

    A planar instance needs nothing: its coordinates *are* a plane. A geodesic
    one carries ``(lat, lon)`` degrees, and drawing those directly puts latitude
    on the x-axis and longitude down the screen -- the map comes out transposed,
    with north pointing right. Degrees are also not a distance: measuring a
    flight in them mixes two differently sized units and reports a number in
    neither.

    So a geodesic instance gets a local tangent-plane projection, in
    **kilometres east and north of the depot**. It is exact enough over a city
    (the error against haversine is below a metre here) and it makes the page's
    scale bar, its grid and its "flown distance" all mean the same thing the
    solver's energies do.

    Returned as data rather than applied in place: the payload's coordinates
    stay the instance's own, and both this module and the page's `toSvg` derive
    the world from these numbers.
    """
    if not inst.geodesic:
        return None
    lat0, lon0 = float(inst.coords[0][0]), float(inst.coords[0][1])
    return {
        "kind": "geodesic",
        "lat0": lat0,
        "lon0": lon0,
        "km_per_deg_lat": KM_PER_DEGREE,
        "km_per_deg_lon": KM_PER_DEGREE * max(math.cos(math.radians(lat0)),
                                              1e-6),
    }


def to_world(proj: Optional[Dict[str, float]],
             xs: Sequence[float],
             ys: Sequence[float]) -> np.ndarray:
    """Instance coordinates as the ``(x, y)`` plane the page measures in."""
    if proj is None:
        return np.column_stack([xs, ys])
    lat = np.asarray(xs, dtype=float)
    lon = np.asarray(ys, dtype=float)
    return np.column_stack([(lon - proj["lon0"]) * proj["km_per_deg_lon"],
                            (lat - proj["lat0"]) * proj["km_per_deg_lat"]])


def _cumulative(pts: np.ndarray) -> List[float]:
    if len(pts) < 2:
        return [0.0] * len(pts)
    seg = np.sqrt(((pts[1:] - pts[:-1]) ** 2).sum(axis=1))
    return [0.0] + list(np.cumsum(seg))


def _flight(inst: DRPInstance, drone: int, route: List[int],
            th: Theme,
            proj: Optional[Dict[str, float]]) -> Dict[str, Any]:
    xs, ys = route_polyline(inst, route)
    cumulative = _cumulative(to_world(proj, xs, ys))
    energy = route_energy(inst, route)
    return {
        "drone": drone,
        "color": th.color(drone),
        # The second channel: a route keeps its identity in greyscale and
        # under any colour-vision deficiency. Indexed on `drone`, exactly as
        # the colour is, so the two never disagree.
        "dash": th.dash(drone),
        "route": [int(c) for c in route],
        "polyline": [[float(x), float(y)] for x, y in zip(xs, ys)],
        "cumulative": [float(c) for c in cumulative],
        "length": float(cumulative[-1]) if cumulative else 0.0,
        "energy": (None if math.isinf(energy) else float(energy)),
        "payload": float(route_weight(inst, route)),
    }


def build_playback_data(inst: DRPInstance,
                        sol: Solution,
                        separation: Optional[float] = None,
                        title: Optional[str] = None,
                        theme=None,
                        basemap: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Everything the playback page needs, as one JSON-serialisable dict.

    `separation` is the distance below which two airborne drones are flagged as
    a conflict; defaults to 3% of the field span, matching
    `drp.viz.animate.animate_routes` so the GIF and the web page agree on what
    counts as a conflict. It is expressed in the same units the page measures
    in -- kilometres for a geodesic instance, raw coordinate units otherwise.

    `theme` is a name or a `drp.viz.theme.Theme`; the whole thing goes into the
    payload under `theme`, and the page writes it into its CSS custom
    properties at startup rather than carrying a palette of its own.

    `basemap` is an optional ``drp-basemap/v1`` mapping from
    `drp.viz.basemap`. Given one, the page draws real streets, water and
    land use in place of the synthetic city it invents; its geometry is
    ``(lat, lon)`` like the instance's, and the page projects both the same way.
    """
    th = resolve(theme)
    proj = projection(inst)
    used = [(k, r) for k, r in enumerate(sol.routes) if r]
    flights = [_flight(inst, k, r, th, proj) for k, r in used]

    co = inst.coords
    world = to_world(proj, co[:, 0], co[:, 1])
    span = max(float(np.ptp(world[:, 0])), float(np.ptp(world[:, 1]))) or 1.0
    if separation is None:
        separation = 0.03 * span

    battery = inst.battery if math.isfinite(inst.battery) else max(
        (f["energy"] for f in flights if f["energy"] is not None), default=1.0)

    payload: Dict[str, Any] = {
        "instance": instance_to_dict(inst),
        "solution": solution_to_dict(inst, sol),
        "theme": th.to_dict(),
        "flights": flights,
        "meta": {
            "title": title or f"{inst.name} -- fleet playback",
            "battery": float(battery),
            "separation": float(separation),
            "projection": proj,
            "units": "km" if proj else "units",
            "bounds": {
                "xmin": float(co[:, 0].min()), "xmax": float(co[:, 0].max()),
                "ymin": float(co[:, 1].min()), "ymax": float(co[:, 1].max()),
            },
            "zones": [[[float(x), float(y)] for x, y in poly]
                      for poly in inst.nofly_zones],
        },
    }
    if basemap is not None:
        payload["basemap"] = basemap
    return payload
