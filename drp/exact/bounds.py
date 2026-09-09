"""Lower bounds for Branch & Bound.

Two bounds, cheap-first:

- `min_in_edge` / `completion_bound` -- O(1)-per-child once the parent's sum is
  known. Charges each unassigned customer its own cheapest entering arc,
  independent of every other customer. Weak, because nothing stops two
  customers from "sharing" the same cheap predecessor in the bound even though
  a real route cannot reuse an arc -- see roadmap §5.1's flat-bound diagnosis
  in PROGRESS.md.

- `assignment_completion_bound` -- an assignment-relaxation (AP) bound,
  O(m^3) via the Hungarian algorithm. It forces a *globally consistent*
  one-predecessor-one-successor structure across all unassigned customers plus
  the open route's continuation and the depot copies for the drones still
  available, so it cannot double-book a cheap arc the way the column-minimum
  bound can. `test_bounds.py::test_assignment_bound_dominates_column_min`
  proves it is never looser: any AP-feasible assignment restricted to just the
  "each customer picks its own cheapest entering arc" freedom is a relaxation
  of the AP's own constraints, so the AP optimum can only be >=.

Both bounds must never exceed the true optimum. `test_bnb_ground_truth.py`
checks that end to end against brute force; a bound that overestimates
silently prunes the optimum and returns a wrong answer labelled "optimal".
"""
from __future__ import annotations

import math
from typing import Iterable, List, Optional

import numpy as np
from scipy.optimize import linear_sum_assignment

from drp.core.instance import DRPInstance

_INF = 1e18


def min_in_edge(inst: DRPInstance) -> List[float]:
    """For each customer, its cheapest entering arc, charged at the weight it
    must be carrying no matter what still comes after it.

    Any completion enters customer `c` exactly once, still holding at least
    `demand[c]` (its own parcel, not yet dropped). So
    `d_min * (alpha + beta * demand[c])` never overestimates that arc's true
    cost, whatever the rest of the route looks like.
    """
    d = inst.dist
    mins = [0.0] * inst.N
    for c in range(1, inst.N):
        best = math.inf
        for j in range(inst.N):
            if j == c or inst.edge_forbidden(j, c):
                continue
            best = min(best, d[j, c])
        if math.isinf(best):
            mins[c] = 0.0
        else:
            mins[c] = best * (inst.alpha + inst.beta * inst.demand[c])
    return mins


def completion_bound(min_in: List[float], unassigned: Iterable[int]) -> float:
    """Optimistic cost of serving everything still unassigned."""
    return sum(min_in[c] for c in unassigned)


def _arc_lb(inst: DRPInstance, i: int, j: int) -> float:
    """Lower bound on the true cost of flying `i -> j` at some point in a
    feasible completion, without knowing the eventual onboard weight.

    `j == 0` (the return leg) is flown empty, so this is exact, not just a
    bound. Otherwise the drone still carries at least `demand[j]`.
    """
    if inst.edge_forbidden(i, j):
        return _INF
    d = inst.dist[i, j]
    if j == 0:
        return d * inst.alpha
    return d * (inst.alpha + inst.beta * inst.demand[j])


def assignment_completion_bound(inst: DRPInstance,
                                 prev: Optional[int],
                                 unassigned: Iterable[int],
                                 routes_left: int) -> float:
    """AP-relaxation lower bound on completing `unassigned` from this node.

    `prev` is the open route's current last stop (`None` if no route is
    open), and `routes_left` is how many more drones may still start a fresh
    route from the depot. Every unassigned customer needs exactly one
    predecessor and one successor arc; `prev` and each available drone supply
    one predecessor slot (a "tail") with no predecessor of its own, and every
    active route -- the open one plus each drone actually used -- needs
    exactly one return-to-depot arc (a "head").

    This is a relaxation of the real completion problem: it drops subtour
    elimination, capacity and battery, so it allows cycles and route shapes no
    feasible solution could use. That is exactly what makes it a valid lower
    bound rather than an exact solve, and exactly why it can still be loose --
    it is a strictly *tighter* relaxation than the column-minimum sum, not an
    exact oracle.
    """
    unassigned = sorted(unassigned)
    m = len(unassigned)
    if m == 0:
        return 0.0

    has_prev = prev is not None
    n_returns = routes_left + (1 if has_prev else 0)
    n_tails = m + (1 if has_prev else 0) + routes_left
    n_heads = m + n_returns
    if n_tails != n_heads or n_tails == 0:
        return math.inf  # no drone available to reach any of `unassigned`

    C = np.full((n_tails, n_heads), _INF)

    # Head columns: unassigned customers, then depot-return slots.
    for hi, j in enumerate(unassigned):
        # Tail rows: unassigned customers (excluding self), then `prev`, then
        # fresh depot-start copies.
        for ti, i in enumerate(unassigned):
            if i != j:
                C[ti, hi] = _arc_lb(inst, i, j)
        row = m
        if has_prev:
            C[row, hi] = _arc_lb(inst, prev, j)
            row += 1
        for _ in range(routes_left):
            C[row, hi] = _arc_lb(inst, 0, j)
            row += 1

    for ri in range(n_returns):
        hi = m + ri
        for ti, i in enumerate(unassigned):
            C[ti, hi] = _arc_lb(inst, i, 0)
        row = m
        if has_prev:
            C[row, hi] = _arc_lb(inst, prev, 0)
            row += 1
        for _ in range(routes_left):
            # An unused drone: depot start matched straight to a depot
            # return, i.e. a route that never flies.
            C[row, hi] = 0.0
            row += 1

    row_ind, col_ind = linear_sum_assignment(C)
    total = float(C[row_ind, col_ind].sum())
    return math.inf if total >= _INF else total
