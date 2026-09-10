"""The fast Split must be the *same* Split (roadmap §5.4).

`drp.meta.split.split` was rewritten to carry a segment's weight, energy and
distance forward instead of rebuilding and re-summing the slice for every
``(i, j, k)``. That is a performance change to the single most load-bearing
function in the package -- the GA, SA and ALNS all decode through it, and
`tests/test_split_optimality.py` proves it optimal, so if the rewrite is not
exactly equivalent then everything downstream moves quietly.

So the previous implementation is kept here verbatim as a reference, and these
tests demand agreement on both the value and the segmentation, across instances
with battery limits, forbidden arcs, polygonal zones and geodesic coordinates.

The rewrite is mathematically identical but sums in a different order, so
floating-point results can differ in the last bits. The DP compares with a
1e-12 epsilon, which is four orders of magnitude above that -- these tests are
what makes that argument checkable rather than merely plausible.
"""
from __future__ import annotations

import math
import random
from typing import List, Optional, Sequence, Tuple

import pytest

from drp.core.energy import route_energy, route_weight
from drp.core.instance import DRPInstance
from drp.core.solution import Solution
from drp.instances import (build_geo_instance, generate_instance,
                           generate_zone_instance)
from drp.instances.geodata import DEFAULT_DATASET
from drp.meta.split import split


def reference_split(inst: DRPInstance,
                    tour: Sequence[int]) -> Tuple[Optional[Solution], float]:
    """The implementation as it stood before the rewrite. Do not optimise."""
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
                    break
                e = route_energy(inst, seg)
                if math.isinf(e):
                    continue
                if e > inst.battery + 1e-9:
                    break
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


def _instances():
    cases = [
        generate_instance("plain", 9, 3, seed=1),
        generate_instance("tight", 12, 3, seed=2, battery_factor=0.55),
        generate_instance("nofly", 10, 3, seed=3, nofly_fraction=0.25),
        generate_zone_instance("zoned", 11, 4, seed=4, n_zones=2),
    ]
    if DEFAULT_DATASET.exists():
        cases.append(build_geo_instance("geo", 10, 3, seed=5,
                                        district="Pontianak City",
                                        road_slot="III"))
    return cases


@pytest.mark.parametrize("inst", _instances(), ids=lambda i: i.name)
def test_the_rewrite_agrees_with_the_old_implementation(inst):
    rng = random.Random(20260910)
    customers = list(range(1, inst.N))

    for _ in range(60):
        tour = customers[:]
        rng.shuffle(tour)

        fast_sol, fast_e = split(inst, tour)
        slow_sol, slow_e = reference_split(inst, tour)

        if slow_sol is None:
            assert fast_sol is None, f"{inst.name}: rewrite found a split the old one did not"
            continue
        assert fast_sol is not None, f"{inst.name}: rewrite lost a feasible split"
        assert fast_e == pytest.approx(slow_e, rel=1e-12, abs=1e-9)
        # Same segmentation, not merely the same total.
        assert fast_sol.used_routes() == slow_sol.used_routes()


def test_agreement_holds_on_tours_that_cannot_be_split():
    """An instance too tight to segment must stay unsplittable."""
    inst = generate_instance("impossible", 8, 2, seed=6)
    inst.battery = 1e-6
    inst.invalidate_distances()

    tour = list(range(1, inst.N))
    assert split(inst, tour)[0] is None
    assert reference_split(inst, tour)[0] is None


def test_the_rewrite_is_substantially_faster():
    """The point of the change, stated as a measurement.

    Not a strict timing assertion -- those are flaky on shared machines -- but
    a floor low enough that only a genuine regression trips it. The observed
    speedup at n = 100 is far larger than this.
    """
    import time

    inst = generate_instance("big", 60, 6, seed=7)
    tour = list(range(1, inst.N))

    t0 = time.perf_counter()
    fast = split(inst, tour)[1]
    fast_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    slow = reference_split(inst, tour)[1]
    slow_time = time.perf_counter() - t0

    assert fast == pytest.approx(slow, rel=1e-12, abs=1e-9)
    assert fast_time < slow_time / 3, (
        f"expected a large speedup, got {slow_time / max(fast_time, 1e-9):.1f}x")
