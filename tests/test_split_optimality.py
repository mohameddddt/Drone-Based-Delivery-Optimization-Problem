"""Split-DP optimality against brute force -- the highest-value test here.

The GA, SA and ALNS all rest on one claim: for a fixed customer ordering, Split
returns the *cheapest* segmentation into at most K feasible routes. If that were
subtly wrong, all three metaheuristics would silently return sub-optimal answers
and nothing else in the project would notice.

So for small tours we enumerate every possible segmentation, take the true
minimum, and assert Split matches it exactly.
"""
from __future__ import annotations

import math
import random
from itertools import combinations
from typing import List, Optional, Sequence, Tuple

import pytest

from drp.core import route_energy, route_weight
from drp.core.instance import DRPInstance
from drp.instances import generate_instance
from drp.meta.construct import warm_start_tour
from drp.meta.split import split


def brute_force_split(inst: DRPInstance,
                      tour: Sequence[int]) -> Tuple[Optional[List[List[int]]], float]:
    """Enumerate every way of cutting `tour` into <= K consecutive segments.

    A segmentation of an n-element tour into k parts is a choice of k-1 cut
    points from the n-1 gaps, so this is exhaustive by construction.
    """
    n = len(tour)
    K = inst.n_drones
    best_routes, best_cost = None, math.inf

    for k in range(1, K + 1):
        if k > n:
            break
        for cuts in combinations(range(1, n), k - 1):
            bounds = (0,) + cuts + (n,)
            segments = [list(tour[bounds[i]:bounds[i + 1]])
                        for i in range(len(bounds) - 1)]
            total = 0.0
            ok = True
            for seg in segments:
                if route_weight(inst, seg) > inst.payload + 1e-9:
                    ok = False
                    break
                e = route_energy(inst, seg)
                if math.isinf(e) or e > inst.battery + 1e-9:
                    ok = False
                    break
                total += e
            if ok and total < best_cost - 1e-12:
                best_cost, best_routes = total, segments

    return best_routes, best_cost


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5, 6, 7, 8])
def test_split_matches_brute_force(seed):
    """Random tours on small instances: Split must equal the true optimum."""
    inst = generate_instance(f"sp{seed}", 8, 3, 100 + seed, nofly_fraction=0.1)
    rng = random.Random(seed)

    for _ in range(12):
        tour = list(range(1, inst.N))
        rng.shuffle(tour)

        _, brute_cost = brute_force_split(inst, tour)
        sol, dp_cost = split(inst, tour)

        if math.isinf(brute_cost):
            assert sol is None or math.isinf(dp_cost), \
                "no feasible segmentation exists, but Split returned one"
            continue

        assert sol is not None, "a feasible segmentation exists but Split found none"
        assert dp_cost == pytest.approx(brute_cost, abs=1e-6), \
            f"Split returned {dp_cost}, true optimum is {brute_cost}"


@pytest.mark.parametrize("seed", [11, 12, 13])
def test_split_result_is_self_consistent(seed):
    """The reported cost must equal the cost of the routes actually returned,
    and those routes must be a partition of the tour in order.

    Uses the greedy construction's tour rather than a random one: a random
    permutation need not admit any feasible segmentation, and Split returning
    None there is correct behaviour, not something to assert against.
    """
    inst = generate_instance(f"sc{seed}", 9, 3, seed)
    tour = warm_start_tour(inst)
    if tour is None:
        pytest.skip("no feasible construction for this instance")

    sol, cost = split(inst, tour)
    assert sol is not None, "the greedy tour must admit a feasible split"

    recomputed = sum(route_energy(inst, r) for r in sol.routes)
    assert recomputed == pytest.approx(cost, abs=1e-9)

    # concatenating the routes must give back the tour, in order
    assert [c for r in sol.routes for c in r] == tour
    assert len(sol.used_routes()) <= inst.n_drones


@pytest.mark.parametrize("seed", [21, 22, 23])
def test_split_respects_fleet_limit(seed):
    inst = generate_instance(f"fl{seed}", 10, 2, seed)
    rng = random.Random(seed)
    tour = list(range(1, inst.N))
    rng.shuffle(tour)
    sol, cost = split(inst, tour)
    if sol is not None:
        assert len(sol.used_routes()) <= inst.n_drones


def test_split_of_empty_tour():
    inst = generate_instance("empty", 5, 2, 1)
    sol, cost = split(inst, [])
    assert cost == 0.0
    assert sol is not None and sol.used_routes() == []
