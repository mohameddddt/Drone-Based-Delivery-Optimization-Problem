"""The assignment-relaxation completion bound (roadmap §5.1).

Three claims:

1. **Dominance.** `assignment_completion_bound` is never looser than the
   column-minimum `completion_bound` it sits alongside in `drp.exact.bnb` --
   it is a genuinely stronger relaxation, not just a different one.
2. **Validity.** It never exceeds the true minimum cost of actually completing
   the unassigned customers, checked against brute-force enumeration of every
   ordering.
3. **The phantom-return regression.** `drp.core.energy.route_energy_open` is
   what makes combining the AP bound with the open route's running cost
   valid: `route_energy` on a route still being extended bakes in a
   return-to-depot leg from whatever customer happens to be last, which is
   never actually flown if the route goes on to take more customers. A tight
   enough completion bound stacked on top of that phantom leg provably
   exceeds the true remaining cost -- this was caught directly by
   `test_bnb_ground_truth.py` reporting a *worse* "proven optimal" energy
   than brute force on `db4/n7k3` before the fix.
"""
from __future__ import annotations

import math
from itertools import permutations

import pytest

from drp.core.energy import route_energy, route_energy_open, route_weight
from drp.exact.bounds import (assignment_completion_bound, completion_bound,
                               min_in_edge)
from drp.instances import generate_instance


@pytest.mark.parametrize("seed,n,k", [(1, 5, 2), (2, 6, 2), (3, 6, 3),
                                       (4, 7, 3), (5, 8, 2)])
def test_assignment_bound_dominates_column_min(seed, n, k):
    """Any AP-feasible matching is also a candidate under the column-minimum
    bound's own freedom (each customer independently picks its own cheapest
    entering arc) -- the AP just adds the constraint that no two customers
    may reuse the same predecessor. A more constrained minimisation can only
    cost the same or more."""
    inst = generate_instance(f"dom{seed}", n, k, 500 + seed)
    min_in = min_in_edge(inst)
    full = frozenset(range(1, inst.N))

    cheap = completion_bound(min_in, full)
    ap = assignment_completion_bound(inst, None, full, inst.n_drones)
    assert ap >= cheap - 1e-6, f"AP bound {ap} is looser than column-min {cheap}"


def _brute_force_completion(inst, prev, unassigned, routes_left):
    """True minimum cost of serving `unassigned`, continuing from `prev` (or
    starting fresh) plus up to `routes_left` new routes -- capacity and
    battery ignored, matching what the AP relaxation itself ignores."""
    unassigned = sorted(unassigned)
    n = len(unassigned)
    best = math.inf
    max_segments = (1 if prev is not None else 0) + routes_left
    for perm in permutations(unassigned):
        for k in range(1, min(max_segments, n) + 1):
            from itertools import combinations
            for cuts in combinations(range(1, n), k - 1):
                bounds_ = (0,) + cuts + (n,)
                segs = [list(perm[bounds_[i]:bounds_[i + 1]])
                       for i in range(len(bounds_) - 1)]
                if prev is not None:
                    first, rest_segs = segs[0], segs[1:]
                    # Cost of continuing from `prev` through `first`, using
                    # only `first`'s own weight (matching the bound's
                    # semantics: no other cargo shares this sub-path).
                    onboard = route_weight(inst, first)
                    total, ok, p = 0.0, True, prev
                    for c in first:
                        e = inst.dist[p, c] * (inst.alpha + inst.beta * onboard)
                        if inst.edge_forbidden(p, c):
                            ok = False
                            break
                        total += e
                        onboard -= inst.demand[c]
                        p = c
                    if not ok:
                        continue
                    total += inst.dist[p, 0] * inst.alpha
                else:
                    rest_segs = segs
                    total = 0.0
                ok = True
                for seg in rest_segs:
                    e = route_energy(inst, seg)
                    if math.isinf(e):
                        ok = False
                        break
                    total += e
                if ok and total < best:
                    best = total
    return best


@pytest.mark.parametrize("seed,prev,m,routes_left", [
    (1, None, 4, 2), (2, 1, 3, 1), (3, 1, 3, 2), (4, None, 3, 3),
])
def test_assignment_bound_never_exceeds_true_completion(seed, prev, m, routes_left):
    inst = generate_instance(f"apv{seed}", 7, 4, 600 + seed)
    unassigned = frozenset(range(1, m + 1))
    if prev is not None and prev in unassigned:
        unassigned = unassigned - {prev}
    truth = _brute_force_completion(inst, prev, unassigned, routes_left)
    if math.isinf(truth):
        pytest.skip("no feasible completion to bound")
    ap = assignment_completion_bound(inst, prev, unassigned, routes_left)
    assert ap <= truth + 1e-6, f"AP bound {ap} exceeds true completion {truth}"


def test_route_energy_open_excludes_the_return_leg():
    inst = generate_instance("open1", 5, 2, 42)
    route = [1, 2]
    assert route_energy_open(inst, route) < route_energy(inst, route)
    return_leg = route_energy(inst, route) - route_energy_open(inst, route)
    expected_return = inst.dist[2, 0] * inst.alpha
    assert return_leg == pytest.approx(expected_return, abs=1e-9)


def test_route_energy_open_of_empty_route_is_zero():
    inst = generate_instance("open2", 5, 2, 43)
    assert route_energy_open(inst, []) == 0.0
