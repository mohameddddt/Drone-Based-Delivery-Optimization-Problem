"""Lower bounds for Branch & Bound.

Currently one bound: the column-minimum (min-in-edge) bound. It is weak, which
is exactly why the search stalls around n = 9 -- see roadmap §5.1, where
Held-Karp 1-trees, an assignment relaxation and the LP relaxation of the flow
formulation are the planned upgrades.

The bound must never exceed the true optimum. `tests/test_bounds.py` asserts
that against brute force, because a bound that overestimates silently prunes the
optimum and returns a wrong answer labelled "optimal".
"""
from __future__ import annotations

import math
from typing import Iterable, List

from drp.core.instance import DRPInstance


def min_in_edge(inst: DRPInstance) -> List[float]:
    """For each customer, `alpha` times its shortest non-forbidden entering edge.

    Any completion must enter every unassigned customer at least once. `alpha`
    is the smallest per-distance coefficient and `beta * w >= 0`, so charging
    `alpha * d_min` per unassigned customer never overestimates.
    """
    d = inst.dist
    mins = [0.0] * inst.N
    for c in range(1, inst.N):
        best = math.inf
        for j in range(inst.N):
            if j == c or inst.edge_forbidden(j, c):
                continue
            best = min(best, d[j, c])
        mins[c] = inst.alpha * (0.0 if math.isinf(best) else best)
    return mins


def completion_bound(min_in: List[float], unassigned: Iterable[int]) -> float:
    """Optimistic cost of serving everything still unassigned."""
    return sum(min_in[c] for c in unassigned)
