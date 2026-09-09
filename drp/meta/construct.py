"""Constructive heuristics -- the warm starts.

Two constructions, both constraint-aware:

  * `nearest_neighbour_routes` -- greedily extend a route with the closest
    customer that keeps it feasible, opening a new drone when nothing fits.
  * `savings_construction` -- Clarke-Wright savings adapted to the energy
    objective, merging route endpoints in decreasing order of savings.

`best_construction` returns the cheaper of the two. Every other method uses it as
a starting point, which makes them all comparable from the same baseline.
"""
from __future__ import annotations

import math
from typing import List, Optional

from drp.core.energy import route_energy, route_weight, total_energy
from drp.core.feasibility import is_feasible
from drp.core.instance import DRPInstance
from drp.core.solution import Solution


def nearest_neighbour_routes(inst: DRPInstance) -> Optional[Solution]:
    """Greedy nearest-neighbour construction. None if it cannot place everyone."""
    d = inst.dist
    unvisited = set(range(1, inst.N))
    routes: List[List[int]] = []

    while unvisited and len(routes) < inst.n_drones:
        route: List[int] = []
        cur = 0
        while True:
            best_c, best_d = None, math.inf
            for c in sorted(unvisited):
                if inst.edge_forbidden(cur, c):
                    continue
                trial = route + [c]
                if route_weight(inst, trial) > inst.payload + 1e-9:
                    continue
                if route_energy(inst, trial) > inst.battery + 1e-9:
                    continue
                if d[cur, c] < best_d:
                    best_d, best_c = d[cur, c], c
            if best_c is None:
                break
            route.append(best_c)
            unvisited.discard(best_c)
            cur = best_c
        if not route:
            break  # nothing fits even in a fresh route
        routes.append(route)

    while len(routes) < inst.n_drones:
        routes.append([])

    sol = Solution(routes)
    return sol if is_feasible(inst, sol)[0] else None


def savings_construction(inst: DRPInstance) -> Optional[Solution]:
    """Clarke-Wright savings, adapted to energy, capacity and no-fly limits."""
    d = inst.dist
    routes: List[List[int]] = [[c] for c in range(1, inst.N)]

    def feasible_route(r) -> bool:
        return (route_weight(inst, r) <= inst.payload + 1e-9
                and route_energy(inst, r) <= inst.battery + 1e-9)

    savings = []
    for i in range(1, inst.N):
        for j in range(1, inst.N):
            if i == j or inst.edge_forbidden(i, j):
                continue
            savings.append((d[i, 0] + d[0, j] - d[i, j], i, j))
    savings.sort(reverse=True)

    def route_of(c: int) -> Optional[int]:
        for idx, r in enumerate(routes):
            if c in r:
                return idx
        return None

    for _s, i, j in savings:
        ri, rj = route_of(i), route_of(j)
        if ri is None or rj is None or ri == rj:
            continue
        if routes[ri][-1] != i or routes[rj][0] != j:
            continue  # i must be a tail and j a head
        merged = routes[ri] + routes[rj]
        if not feasible_route(merged):
            continue
        routes[ri] = merged
        routes.pop(rj)

    if len(routes) > inst.n_drones:
        return nearest_neighbour_routes(inst)

    while len(routes) < inst.n_drones:
        routes.append([])
    sol = Solution(routes)
    return sol if is_feasible(inst, sol)[0] else nearest_neighbour_routes(inst)


def best_construction(inst: DRPInstance) -> Optional[Solution]:
    """The cheaper of the two constructions, or None if neither is feasible."""
    cands = [s for s in (nearest_neighbour_routes(inst),
                         savings_construction(inst)) if s is not None]
    if not cands:
        return None
    return min(cands, key=lambda s: total_energy(inst, s))


def warm_start_tour(inst: DRPInstance) -> Optional[List[int]]:
    """The greedy solution flattened into a giant tour, for the metaheuristics."""
    sol = best_construction(inst)
    return None if sol is None else sol.giant_tour()
