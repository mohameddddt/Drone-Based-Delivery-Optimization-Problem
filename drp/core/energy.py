"""The energy model -- the one place cost is defined.

Traversing an arc of length ``d`` while carrying weight ``w`` costs

    e(d, w) = d * (alpha + beta * w)

A drone loads its whole route's demand at the depot and sheds weight at each
delivery, so the onboard weight decreases along the route and the total energy
depends on the *order* of visits, not just on which customers are grouped
together. That order-dependence is what separates this problem from a plain
distance-based VRP.

Every method in the package -- exact and heuristic alike -- calls into this
module, so comparisons between them are fair by construction.
"""
from __future__ import annotations

import math
from typing import List, Sequence

from drp.core.instance import DRPInstance
from drp.core.solution import Solution


def leg_energy(inst: DRPInstance, i: int, j: int, onboard: float) -> float:
    """Energy to fly from node `i` to node `j` carrying `onboard` weight."""
    if inst.edge_forbidden(i, j):
        return math.inf
    return inst.dist[i, j] * (inst.alpha + inst.beta * onboard)


def route_weight(inst: DRPInstance, route: Sequence[int]) -> float:
    """Total payload a drone must lift to fly `route`."""
    return float(sum(inst.demand[c] for c in route))


def route_energy(inst: DRPInstance, route: Sequence[int]) -> float:
    """Energy of one route, accounting for the decreasing payload.

    Returns ``inf`` if the route uses a forbidden arc.
    """
    if not route:
        return 0.0
    onboard = route_weight(inst, route)
    total = 0.0
    prev = 0
    for c in route:
        e = leg_energy(inst, prev, c, onboard)
        if math.isinf(e):
            return math.inf
        total += e
        onboard -= inst.demand[c]
        prev = c
    # the return leg is flown empty
    e = leg_energy(inst, prev, 0, onboard)
    if math.isinf(e):
        return math.inf
    return total + e


def route_energy_trace(inst: DRPInstance, route: Sequence[int]) -> List[dict]:
    """Per-leg breakdown of a route, for reporting and visualisation."""
    trace: List[dict] = []
    if not route:
        return trace
    onboard = route_weight(inst, route)
    prev = 0
    for c in list(route) + [0]:
        d = inst.dist[prev, c]
        e = leg_energy(inst, prev, c, onboard)
        trace.append({"from": int(prev), "to": int(c), "distance": float(d),
                      "onboard": float(onboard), "energy": float(e)})
        if c != 0:
            onboard -= inst.demand[c]
        prev = c
    return trace


def total_energy(inst: DRPInstance, sol: Solution) -> float:
    """Fleet energy: the sum over routes."""
    return sum(route_energy(inst, r) for r in sol.routes)
