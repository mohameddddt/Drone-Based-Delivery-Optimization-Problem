"""Feasibility checking and the penalised objective.

`is_feasible` is the referee: a solution is feasible when every customer is
served exactly once, no more than the available drones fly, and every route
respects payload, battery and no-fly limits.

`evaluate` is the softened version used inside metaheuristics that are allowed
to pass through infeasible territory. Note that the metaheuristics in this
package do *not* rely on it -- their Split decoder only ever emits feasible
solutions -- but it is kept for search strategies that want the freedom.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Tuple

from drp.core.energy import route_energy, route_weight, total_energy
from drp.core.instance import EPS, DRPInstance
from drp.core.solution import Solution


def is_feasible(inst: DRPInstance, sol: Solution) -> Tuple[bool, str]:
    """Full feasibility check. Returns ``(ok, reason)``."""
    if sol is None:
        return False, "no solution"

    served = sorted(sol.customers())
    if served != list(range(1, inst.N)):
        return False, "customers not served exactly once"

    used = sol.used_routes()
    if len(used) > inst.n_drones:
        return False, f"uses {len(used)} drones > fleet {inst.n_drones}"

    for r in sol.routes:
        if route_weight(inst, r) > inst.payload + EPS:
            return False, "payload capacity exceeded"
        if route_energy(inst, r) > inst.battery + EPS:  # inf if a no-fly arc is used
            return False, "battery capacity exceeded or no-fly arc used"

    return True, "feasible"


def feasibility_certificate(inst: DRPInstance, sol: Solution) -> dict:
    """A machine-readable record of *why* a solution is (in)feasible.

    Written into the solution file so a third party can check a claimed result
    without re-running any solver.
    """
    ok, reason = is_feasible(inst, sol)
    per_route = []
    for k, r in enumerate(sol.routes):
        if not r:
            continue
        e = route_energy(inst, r)
        w = route_weight(inst, r)
        per_route.append({
            "drone": k,
            "customers": [int(c) for c in r],
            "energy": None if math.isinf(e) else float(e),
            "weight": float(w),
            "battery_ok": bool(e <= inst.battery + EPS),
            "payload_ok": bool(w <= inst.payload + EPS),
        })
    return {
        "feasible": ok,
        "reason": reason,
        "total_energy": float(total_energy(inst, sol)),
        "drones_used": len(sol.used_routes()),
        "fleet_size": inst.n_drones,
        "routes": per_route,
    }


def evaluate(inst: DRPInstance, sol: Solution, penalty: float = 1e6) -> float:
    """Penalised objective: energy plus a penalty for each violation."""
    cnt = Counter(sol.customers())
    pen = 0.0
    for c in range(1, inst.N):
        if cnt[c] == 0:
            pen += penalty
        elif cnt[c] > 1:
            pen += penalty * (cnt[c] - 1)

    used = len(sol.used_routes())
    if used > inst.n_drones:
        pen += penalty * (used - inst.n_drones)

    e = 0.0
    for r in sol.routes:
        re = route_energy(inst, r)
        if math.isinf(re):
            pen += penalty
            continue
        e += re
        pen += penalty * max(0.0, route_weight(inst, r) - inst.payload)
        pen += penalty * max(0.0, re - inst.battery) / max(inst.battery, 1.0)

    return e + pen
