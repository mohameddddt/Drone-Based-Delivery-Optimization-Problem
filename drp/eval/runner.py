"""The experiment runner: one place that knows how to invoke every method.

`solve_one` wraps each solver into a common `MethodResult`, so callers -- the
CLI, the study script, the tests -- never special-case a particular algorithm.
`run_study` sweeps methods x instances x seeds into a `ResultStore`.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from drp.core.energy import total_energy
from drp.core.feasibility import is_feasible
from drp.core.instance import DRPInstance
from drp.core.solution import Solution
from drp.eval.store import ResultStore, RunRecord
from drp.exact.bnb import solve_bnb
from drp.meta.alns import solve_alns
from drp.meta.construct import best_construction
from drp.meta.ga import solve_ga
from drp.meta.sa import solve_sa

METHODS = ("greedy", "bnb", "ga", "sa", "alns")


@dataclass
class MethodResult:
    method: str
    energy: float = math.inf
    solution: Optional[Solution] = None
    feasible: bool = False
    wall_time: float = 0.0
    dual_bound: Optional[float] = None
    optimal: bool = False
    nodes: Optional[int] = None
    iterations: Optional[int] = None
    history: List[float] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


def solve_one(inst: DRPInstance,
              method: str,
              seed: int = 1,
              time_limit: float = 5.0,
              warm: bool = True) -> MethodResult:
    """Run one method on one instance and normalise the outcome."""
    method = method.lower()
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; choose from {METHODS}")

    ws = best_construction(inst) if warm else None
    wt = ws.giant_tour() if ws else None

    t0 = time.time()
    if method == "greedy":
        sol = ws if ws is not None else best_construction(inst)
        e = total_energy(inst, sol) if sol else math.inf
        res = MethodResult("greedy", energy=e, solution=sol)

    elif method == "bnb":
        r = solve_bnb(inst, time_limit=time_limit, warm_start=ws)
        res = MethodResult("bnb", energy=r.best_energy, solution=r.best_solution,
                           dual_bound=r.dual_bound, optimal=r.optimal,
                           nodes=r.nodes_explored)

    elif method == "ga":
        r = solve_ga(inst, seed=seed, time_limit=time_limit,
                     warm_tours=[wt] if wt else None)
        res = MethodResult("ga", energy=r.best_energy, solution=r.best_solution,
                           iterations=r.generations, history=r.history)

    elif method == "sa":
        r = solve_sa(inst, seed=seed, time_limit=time_limit, warm_tour=wt)
        res = MethodResult("sa", energy=r.best_energy, solution=r.best_solution,
                           iterations=r.iterations, history=r.history,
                           extra={"reheats": r.reheats})

    else:  # alns
        r = solve_alns(inst, seed=seed, time_limit=time_limit, warm_tour=wt)
        res = MethodResult("alns", energy=r.best_energy, solution=r.best_solution,
                           iterations=r.iterations, history=r.history,
                           extra={"destroy_weights": r.destroy_weights,
                                  "repair_weights": r.repair_weights})

    res.wall_time = time.time() - t0
    res.feasible = bool(res.solution is not None
                        and is_feasible(inst, res.solution)[0])
    return res


def run_study(instances: Sequence[DRPInstance],
              methods: Sequence[str] = METHODS,
              seeds: Sequence[int] = (1, 2, 3, 4, 5),
              time_limit: float = 5.0,
              bnb_time_limit: Optional[float] = None,
              store: Optional[ResultStore] = None,
              run_group: Optional[str] = None,
              progress: Optional[Callable[[str], None]] = None) -> ResultStore:
    """Sweep methods x instances x seeds, recording every run.

    Deterministic methods (greedy, B&B) are run once per instance rather than
    once per seed, since extra seeds would only duplicate work.
    """
    store = store or ResultStore()
    run_group = run_group or time.strftime("run_%Y%m%d_%H%M%S")
    bnb_time_limit = time_limit if bnb_time_limit is None else bnb_time_limit

    for inst in instances:
        for method in methods:
            deterministic = method in ("greedy", "bnb")
            budget = bnb_time_limit if method == "bnb" else time_limit
            use_seeds = [seeds[0]] if deterministic else list(seeds)
            for seed in use_seeds:
                r = solve_one(inst, method, seed=seed, time_limit=budget)
                store.add(RunRecord(
                    instance=inst.name, method=method,
                    n=inst.n_customers, k=inst.n_drones,
                    seed=(None if deterministic else seed),
                    time_budget=budget,
                    energy=(None if math.isinf(r.energy) else r.energy),
                    dual_bound=r.dual_bound, optimal=r.optimal,
                    feasible=r.feasible, nodes=r.nodes,
                    iterations=r.iterations, wall_time=r.wall_time,
                    run_group=run_group, extra=r.extra,
                ))
            if progress:
                progress(f"{inst.name:14s} {method:7s} done")
    return store
