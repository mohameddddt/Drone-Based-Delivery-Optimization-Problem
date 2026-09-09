"""The Split decoder -- the backbone of every metaheuristic here.

A chromosome is a *giant tour*: a permutation of all customers with no route
delimiters. Split cuts it into the energy-optimal set of at most K feasible
routes, by dynamic programming on an auxiliary acyclic graph.

  * Node ``i`` means "the first ``i`` customers of the tour are covered".
  * Arc ``i -> j`` is one drone route serving tour positions ``i+1..j`` in that
    order, weighted by that route's energy, or forbidden if the segment breaks
    payload, battery or a no-fly arc.

Any path ``0 -> ... -> n`` is a partition of the tour into consecutive routes
whose total arc weight is the fleet energy, so the shortest such path is the
optimal segmentation *for that ordering*. The DP carries a second index, giving
states ``(i, k)`` = "first i customers covered using exactly k routes"; the
answer is ``min over k <= K of dp[n][k]``, so the fleet limit is enforced
exactly rather than by penalty.

This is why the GA and SA operators can be simple: crossover and mutation act on
permutations and are therefore always valid, and every feasibility question is
answered inside Split. `tests/test_split_optimality.py` brute-forces every
segmentation for small tours and asserts Split matches -- the highest-value test
in the repository, since both metaheuristics rest on this being exactly optimal.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from drp.core.energy import route_energy, route_weight
from drp.core.instance import DRPInstance
from drp.core.solution import Solution


def split(inst: DRPInstance,
          tour: Sequence[int]) -> Tuple[Optional[Solution], float]:
    """Optimally segment `tour` into at most K feasible routes.

    Returns ``(solution, energy)``, or ``(None, inf)`` if no segmentation into
    K or fewer feasible routes exists.
    """
    n = len(tour)
    if n == 0:
        return Solution([[] for _ in range(inst.n_drones)]), 0.0

    K = inst.n_drones
    INF = math.inf
    dp = [[INF] * (K + 1) for _ in range(n + 1)]
    parent = [[-1] * (K + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0

    for i in range(n):
        for k in range(K):
            if dp[i][k] == INF:
                continue
            for j in range(i + 1, n + 1):
                seg = list(tour[i:j])
                if route_weight(inst, seg) > inst.payload + 1e-9:
                    break  # extending the segment only adds weight
                e = route_energy(inst, seg)
                if math.isinf(e):
                    continue  # a no-fly arc inside; a longer segment may differ
                if e > inst.battery + 1e-9:
                    break  # and only costs more from here
                if dp[i][k] + e < dp[j][k + 1] - 1e-12:
                    dp[j][k + 1] = dp[i][k] + e
                    parent[j][k + 1] = i

    best_k, best_e = -1, INF
    for k in range(1, K + 1):
        if dp[n][k] < best_e:
            best_e, best_k = dp[n][k], k
    if best_k == -1:
        return None, INF

    routes: List[List[int]] = []
    j, k = n, best_k
    while k > 0:
        i = parent[j][k]
        routes.append(list(tour[i:j]))
        j, k = i, k - 1
    routes.reverse()
    while len(routes) < inst.n_drones:
        routes.append([])
    return Solution(routes), best_e


def split_energy(inst: DRPInstance, tour: Sequence[int]) -> float:
    """Just the cost -- the fitness function for the metaheuristics."""
    return split(inst, tour)[1]
