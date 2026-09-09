"""Formulation 2 -- the commodity-flow MILP, solved with CBC via PuLP.

This is a genuinely different model from the arc-based Formulation 1, not a
reformulation of it. F1 *sequences* nodes with an ordering potential (x, u);
F2 *conserves commodity* with traversal counts (g, y) and has no ordering
variable at all.

A single commodity of undelivered packages flows out of the depot and is
absorbed by customers:

    min  sum_ij d_ij (alpha y_ij + beta g_ij)
    s.t. commodity conservation   (depot emits total demand, customer i absorbs q_i)
         g_ij <= Q y_ij           (capacity linking)
         sum_j y_ij = sum_j y_ji  (drone continuity)
         sum_j y_0j <= K          (fleet size)

The per-route battery limit is a *path* constraint that this model does not
carry, so its optimum is a valid **lower bound** on the true optimum: it agrees
exactly with Branch & Bound when the battery does not bind, and falls below it
when the battery is active. `tests/test_cross_validation.py` asserts that
relationship rather than merely printing it.
"""
from __future__ import annotations

from typing import Optional, Tuple

from drp.core.instance import DRPInstance


def solve_formulation2(inst: DRPInstance,
                       time_limit: float = 60.0,
                       max_customers: int = 8) -> Tuple[Optional[float], str]:
    """Solve the commodity-flow MILP. Returns ``(objective, status)``.

    Guarded to small instances: the model has O(n^2) integer variables and CBC
    slows sharply beyond a handful of customers.
    """
    if inst.n_customers > max_customers:
        return None, f"skipped (n > {max_customers})"
    try:
        import pulp
    except ImportError:
        return None, "pulp not installed -- pip install pulp"

    N = inst.N
    d = inst.dist
    alpha, beta = inst.alpha, inst.beta

    arcs = [(i, j) for i in range(N) for j in range(N)
            if i != j and not inst.edge_forbidden(i, j)]
    if not arcs:
        return None, "no usable arcs"

    prob = pulp.LpProblem("DRP_F2", pulp.LpMinimize)

    g = {a: pulp.LpVariable(f"g_{a[0]}_{a[1]}", lowBound=0) for a in arcs}
    y = {a: pulp.LpVariable(f"y_{a[0]}_{a[1]}", lowBound=0,
                            cat=("Integer" if 0 in a else "Binary"))
         for a in arcs}

    prob += pulp.lpSum(d[i, j] * (alpha * y[(i, j)] + beta * g[(i, j)])
                       for (i, j) in arcs)

    out_arcs = {i: [] for i in range(N)}
    in_arcs = {i: [] for i in range(N)}
    for (i, j) in arcs:
        out_arcs[i].append((i, j))
        in_arcs[j].append((i, j))

    total_q = float(sum(inst.demand[c] for c in range(1, N)))
    for i in range(N):
        rhs = total_q if i == 0 else -float(inst.demand[i])
        prob += (pulp.lpSum(g[a] for a in out_arcs[i])
                 - pulp.lpSum(g[a] for a in in_arcs[i]) == rhs), f"comm_{i}"

    for a in arcs:
        prob += g[a] <= inst.payload * y[a], f"cap_{a[0]}_{a[1]}"

    for i in range(1, N):
        prob += (pulp.lpSum(y[a] for a in out_arcs[i])
                 == pulp.lpSum(y[a] for a in in_arcs[i])), f"cont_{i}"

    prob += pulp.lpSum(y[a] for a in out_arcs[0]) <= inst.n_drones, "fleet"

    prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=time_limit))
    obj = pulp.value(prob.objective)
    return (None if obj is None else float(obj)), pulp.LpStatus[prob.status]
