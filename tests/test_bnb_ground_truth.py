"""Branch & Bound against exhaustive enumeration, and bound validity.

Two separate claims, both critical:

1. On instances small enough to enumerate completely, B&B returns exactly the
   true optimum. A bug in the branching or the symmetry break would show here.

2. The lower bound never exceeds the true optimum. This one matters more than it
   looks: an over-tight bound prunes the branch containing the optimum and the
   search then reports a *wrong* answer labelled "proven optimal". Nothing else
   in the project would detect that -- the number would simply be quietly wrong.
"""
from __future__ import annotations

import math
from itertools import permutations
from typing import List, Optional, Tuple

import pytest

from drp.core import route_energy, route_weight
from drp.core.instance import DRPInstance
from drp.exact.bnb import solve_bnb
from drp.exact.bounds import completion_bound, min_in_edge
from drp.instances import generate_instance
from drp.meta.construct import best_construction


def brute_force_optimum(inst: DRPInstance) -> Tuple[Optional[List[List[int]]], float]:
    """The true optimum, by enumerating every partition into ordered routes.

    Enumerates each permutation of the customers and every way of cutting it
    into at most K consecutive routes. Every partition-into-ordered-routes
    appears as some (permutation, cut) pair, so this is exhaustive.
    """
    customers = list(range(1, inst.N))
    n = len(customers)
    K = inst.n_drones
    best_routes, best_cost = None, math.inf

    from itertools import combinations

    for perm in permutations(customers):
        for k in range(1, min(K, n) + 1):
            for cuts in combinations(range(1, n), k - 1):
                bounds = (0,) + cuts + (n,)
                segments = [list(perm[bounds[i]:bounds[i + 1]])
                            for i in range(len(bounds) - 1)]
                total, ok = 0.0, True
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


@pytest.mark.parametrize("seed,n,k", [(1, 5, 2), (2, 6, 2), (3, 6, 3), (4, 7, 3)])
def test_bnb_matches_brute_force(seed, n, k):
    inst = generate_instance(f"gt{seed}", n, k, 300 + seed)
    _, truth = brute_force_optimum(inst)
    res = solve_bnb(inst, time_limit=120.0, warm_start=best_construction(inst))

    assert res.optimal, "B&B did not finish on an instance this small"
    assert res.best_energy == pytest.approx(truth, abs=1e-6), \
        f"B&B says {res.best_energy}, exhaustive search says {truth}"


@pytest.mark.parametrize("seed,n,k", [(5, 5, 2), (6, 6, 2), (7, 6, 3)])
def test_bnb_matches_brute_force_with_nofly(seed, n, k):
    inst = generate_instance(f"gtn{seed}", n, k, 400 + seed, nofly_fraction=0.15)
    _, truth = brute_force_optimum(inst)
    res = solve_bnb(inst, time_limit=120.0, warm_start=best_construction(inst))

    if math.isinf(truth):
        assert res.best_solution is None or math.isinf(res.best_energy)
        return
    assert res.optimal
    assert res.best_energy == pytest.approx(truth, abs=1e-6)


@pytest.mark.parametrize("seed,n,k", [(1, 5, 2), (2, 6, 2), (3, 6, 3), (4, 7, 3)])
def test_root_bound_never_exceeds_optimum(seed, n, k):
    """The root lower bound must not exceed the true optimum."""
    inst = generate_instance(f"lb{seed}", n, k, 300 + seed)
    _, truth = brute_force_optimum(inst)
    if math.isinf(truth):
        pytest.skip("infeasible instance")

    root = completion_bound(min_in_edge(inst), range(1, inst.N))
    assert root <= truth + 1e-6, \
        f"root bound {root} exceeds the true optimum {truth}"


@pytest.mark.parametrize("seed,n,k", [(1, 5, 2), (3, 6, 3), (4, 7, 3)])
def test_reported_dual_bound_is_valid(seed, n, k):
    """The anytime dual bound must bracket the optimum from below, whether or
    not the search had time to finish."""
    inst = generate_instance(f"db{seed}", n, k, 300 + seed)
    _, truth = brute_force_optimum(inst)
    if math.isinf(truth):
        pytest.skip("infeasible instance")

    for limit in (0.001, 0.01, 120.0):
        res = solve_bnb(inst, time_limit=limit,
                        warm_start=best_construction(inst))
        assert res.dual_bound <= truth + 1e-6, (
            f"dual bound {res.dual_bound} exceeds the optimum {truth} "
            f"at time limit {limit}")
        assert res.best_energy >= truth - 1e-6, (
            f"B&B reported {res.best_energy}, below the true optimum {truth}")
        if res.optimal:
            assert res.best_energy == pytest.approx(truth, abs=1e-6)
            assert res.gap == pytest.approx(0.0, abs=1e-9)


def test_warm_start_never_worsens_the_answer():
    """A warm start may only help: the returned energy must be at most the
    warm start's own energy."""
    from drp.core import total_energy
    inst = generate_instance("warm", 8, 3, 777)
    ws = best_construction(inst)
    res = solve_bnb(inst, time_limit=10.0, warm_start=ws)
    assert res.best_energy <= total_energy(inst, ws) + 1e-9
