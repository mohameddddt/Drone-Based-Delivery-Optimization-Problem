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

    # Locals: this loop is the hot spot of every metaheuristic in the package.
    d = inst.dist
    demand = inst.demand
    alpha, beta = inst.alpha, inst.beta
    payload, battery = inst.payload, inst.battery
    forbidden = inst.edge_forbidden

    for i in range(n):
        row = dp[i]
        if all(v == INF for v in row):
            continue          # this prefix is unreachable; no segment from it counts

        # A segment is extended one customer at a time, carrying its weight,
        # its open energy and its distance-from-depot forward. The alternative
        # -- rebuilding the slice and re-summing it for every (i, j) -- is what
        # made this O(K n^3): the same segment was recomputed once per k, and
        # each recomputation walked the whole segment again.
        #
        # Appending customer c of demand q to a segment does two things: every
        # leg already flown now carries q more (hence beta*q*dist_open), and one
        # new leg is flown carrying exactly q. That is the whole update, and it
        # is O(1).
        weight = 0.0
        dist_open = 0.0        # depot -> ... -> last customer, no return leg
        e_open = 0.0           # energy of those legs, at their final loads
        prev = 0

        for j in range(i + 1, n + 1):
            c = tour[j - 1]
            q = demand[c]

            weight += q
            if weight > payload + 1e-9:
                break          # extending the segment only adds weight
            if forbidden(prev, c):
                break          # an interior leg no longer segment can avoid

            leg = d[prev, c]
            e_open += beta * q * dist_open + leg * (alpha + beta * q)
            dist_open += leg
            prev = c

            if e_open > battery + 1e-9:
                break          # the return leg can only add to this
            if forbidden(c, 0):
                continue       # cannot close here; a longer segment may close

            e = e_open + d[c, 0] * alpha
            if e > battery + 1e-9:
                break          # and only costs more from here

            for k in range(K):
                base = row[k]
                if base == INF:
                    continue
                if base + e < dp[j][k + 1] - 1e-12:
                    dp[j][k + 1] = base + e
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
