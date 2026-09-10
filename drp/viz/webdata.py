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
from typing import Any, Dict, List, Optional

import numpy as np

from drp.core.energy import route_energy, route_weight
from drp.core.instance import DRPInstance
from drp.core.solution import Solution
from drp.instances.io import instance_to_dict, solution_to_dict
from drp.viz.static import PALETTE, route_polyline


def _cumulative(xs: List[float], ys: List[float]) -> List[float]:
    if len(xs) < 2:
        return [0.0] * len(xs)
    pts = np.column_stack([xs, ys])
    seg = np.sqrt(((pts[1:] - pts[:-1]) ** 2).sum(axis=1))
    return [0.0] + list(np.cumsum(seg))


def _flight(inst: DRPInstance, drone: int, route: List[int]) -> Dict[str, Any]:
    xs, ys = route_polyline(inst, route)
    cumulative = _cumulative(xs, ys)
    energy = route_energy(inst, route)
    return {
        "drone": drone,
        "color": PALETTE[drone % len(PALETTE)],
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
                        title: Optional[str] = None) -> Dict[str, Any]:
    """Everything the playback page needs, as one JSON-serialisable dict.

    `separation` is the distance below which two airborne drones are flagged as
    a conflict; defaults to 3% of the field span, matching
    `drp.viz.animate.animate_routes` so the GIF and the web page agree on what
    counts as a conflict.
    """
    used = [(k, r) for k, r in enumerate(sol.routes) if r]
    flights = [_flight(inst, k, r) for k, r in used]

    co = inst.coords
    span = max(float(np.ptp(co[:, 0])), float(np.ptp(co[:, 1]))) or 1.0
    if separation is None:
        separation = 0.03 * span

    battery = inst.battery if math.isfinite(inst.battery) else max(
        (f["energy"] for f in flights if f["energy"] is not None), default=1.0)

    return {
        "instance": instance_to_dict(inst),
        "solution": solution_to_dict(inst, sol),
        "flights": flights,
        "meta": {
            "title": title or f"{inst.name} -- fleet playback",
            "battery": float(battery),
            "separation": float(separation),
            "bounds": {
                "xmin": float(co[:, 0].min()), "xmax": float(co[:, 0].max()),
                "ymin": float(co[:, 1].min()), "ymax": float(co[:, 1].max()),
            },
            "zones": [[[float(x), float(y)] for x, y in poly]
                      for poly in inst.nofly_zones],
        },
    }
