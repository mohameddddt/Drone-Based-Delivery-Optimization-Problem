"""Simulated Annealing over giant tours.

Local search on the same encoding as the GA, so the two are directly comparable.
SA extends plain descent by accepting a worsening move of size ``delta`` with
probability ``exp(-delta / T)``, which lets it escape the local optima that trap
hill-climbing.

The neighbourhood is compound -- 2-opt reversal, swap, or-move -- drawn at
random each iteration. Cooling is geometric, and the initial temperature is
calibrated from the average observed move delta so that early acceptance is
about `init_accept`. On stagnation the search reheats and restarts from the
incumbent, which adds diversification without losing the best solution found.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from drp.core.instance import DRPInstance
from drp.core.solution import Solution
from drp.meta.encoding import random_neighbour, random_tour
from drp.meta.split import split


@dataclass
class SAResult:
    best_solution: Optional[Solution] = None
    best_energy: float = math.inf
    history: List[float] = field(default_factory=list)
    iterations: int = 0
    time: float = 0.0
    reheats: int = 0
    accepted: int = 0
    accepted_uphill: int = 0


def solve_sa(inst: DRPInstance,
             seed: int = 0,
             max_iter: int = 60000,
             gamma: float = 0.9995,
             init_accept: float = 0.8,
             reheat_after: int = 4000,
             time_limit: float = 30.0,
             warm_tour: Optional[Sequence[int]] = None) -> SAResult:
    rng = random.Random(seed)
    t0 = time.time()
    res = SAResult()

    def energy_of(tour: Sequence[int]):
        sol, e = split(inst, tour)
        return e, sol

    cur = list(warm_tour) if warm_tour else random_tour(inst, rng)
    cur_e, cur_sol = energy_of(cur)
    tries = 0
    while math.isinf(cur_e) and tries < 200:
        cur = random_tour(inst, rng)
        cur_e, cur_sol = energy_of(cur)
        tries += 1

    best, best_e, best_sol = cur[:], cur_e, cur_sol

    # Calibrate the starting temperature so that early acceptance ~ init_accept.
    deltas = []
    for _ in range(60):
        ce, _ = energy_of(random_neighbour(cur, rng))
        if not math.isinf(ce):
            deltas.append(abs(ce - cur_e))
    avg_delta = (sum(deltas) / len(deltas)) if deltas else 1.0
    T = T0 = -avg_delta / math.log(init_accept) if avg_delta > 0 else 1.0

    stagnation = 0
    for it in range(max_iter):
        if time.time() - t0 > time_limit:
            break
        cand = random_neighbour(cur, rng)
        ce, csol = energy_of(cand)
        if math.isinf(ce):
            continue
        delta = ce - cur_e
        if delta < 0 or rng.random() < math.exp(-delta / max(T, 1e-9)):
            cur, cur_e, cur_sol = cand, ce, csol
            res.accepted += 1
            if delta > 0:
                res.accepted_uphill += 1
            if cur_e < best_e - 1e-9:
                best, best_e, best_sol = cur[:], cur_e, cur_sol
                stagnation = 0
            else:
                stagnation += 1
        else:
            stagnation += 1

        T *= gamma
        if stagnation >= reheat_after:
            T = T0 * 0.5
            stagnation = 0
            res.reheats += 1
            cur, cur_e, cur_sol = best[:], best_e, best_sol

        if it % 200 == 0:
            res.history.append(best_e)
        res.iterations = it + 1

    res.best_solution = best_sol
    res.best_energy = best_e
    res.time = time.time() - t0
    return res
