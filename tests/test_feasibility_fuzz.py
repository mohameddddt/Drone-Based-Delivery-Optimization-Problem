"""Feasibility fuzzing against an independent reference checker.

`is_feasible` is the referee for the whole project, so it gets a second opinion:
a deliberately naive, slow, independently written checker. Thousands of random
solutions -- valid, invalid, and pathological -- must be judged identically by
both. Where they disagree, one of them is wrong.

The reference implementation is written to be obviously correct rather than
fast, and it does not share code with the implementation under test.
"""
from __future__ import annotations

import math
import random
from typing import List, Tuple

import pytest

from drp.core import Solution, is_feasible
from drp.core.instance import DRPInstance
from drp.instances import generate_instance


def reference_is_feasible(inst: DRPInstance, sol: Solution) -> bool:
    """A slow, independent feasibility checker. Deliberately naive."""
    # 1. every customer exactly once
    flat: List[int] = []
    for r in sol.routes:
        flat.extend(r)
    for c in range(1, inst.N):
        if flat.count(c) != 1:
            return False
    if len(flat) != inst.n_customers:
        return False

    # 2. fleet size
    if sum(1 for r in sol.routes if len(r) > 0) > inst.n_drones:
        return False

    for r in sol.routes:
        if not r:
            continue
        # 3. payload
        w = 0.0
        for c in r:
            w += inst.demand[c]
        if w > inst.payload + 1e-9:
            return False

        # 4. energy, recomputed from scratch
        nodes = [0] + list(r) + [0]
        carried = w
        e = 0.0
        for a, b in zip(nodes[:-1], nodes[1:]):
            lo, hi = (a, b) if a < b else (b, a)
            if (lo, hi) in inst.nofly_edges:
                return False
            d = inst.dist[a][b]
            if math.isinf(d):
                return False
            e += d * (inst.alpha + inst.beta * carried)
            if b != 0:
                carried -= inst.demand[b]
        if e > inst.battery + 1e-9:
            return False

    return True


def random_solution(inst: DRPInstance, rng: random.Random) -> Solution:
    """A random partition of the customers -- usually infeasible, by design."""
    customers = list(range(1, inst.N))
    rng.shuffle(customers)

    mode = rng.random()
    if mode < 0.15:                      # duplicate a customer
        customers.append(rng.choice(customers))
    elif mode < 0.30 and len(customers) > 1:   # drop one
        customers.pop()

    n_routes = rng.randint(1, inst.n_drones + 2)   # sometimes too many drones
    routes: List[List[int]] = [[] for _ in range(n_routes)]
    for c in customers:
        routes[rng.randrange(n_routes)].append(c)
    return Solution(routes)


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5, 6])
def test_fuzz_matches_reference_checker(seed):
    inst = generate_instance(f"fz{seed}", 9, 3, 600 + seed, nofly_fraction=0.1)
    rng = random.Random(seed)

    agreed = 0
    feasible_seen = 0
    for _ in range(400):
        sol = random_solution(inst, rng)
        mine = is_feasible(inst, sol)[0]
        theirs = reference_is_feasible(inst, sol)
        assert mine == theirs, (
            f"disagreement on {sol.routes}: is_feasible={mine}, reference={theirs}")
        agreed += 1
        feasible_seen += int(mine)

    assert agreed == 400
    # the fuzzer must actually produce some feasible solutions, or it is only
    # testing the rejection path
    assert feasible_seen > 0, "fuzzer never generated a feasible solution"


@pytest.mark.parametrize("seed", [11, 12, 13])
def test_solver_outputs_pass_the_reference_checker(seed):
    """Anything a solver calls feasible must satisfy the independent checker."""
    from drp.eval.runner import solve_one

    inst = generate_instance(f"so{seed}", 9, 3, 700 + seed, nofly_fraction=0.1)
    for method in ("greedy", "bnb", "ga", "sa", "alns"):
        res = solve_one(inst, method, seed=seed, time_limit=2.0)
        if res.solution is None or not res.feasible:
            continue
        assert reference_is_feasible(inst, res.solution), (
            f"{method} returned a solution it believes is feasible, but the "
            f"reference checker rejects it: {res.solution.routes}")
