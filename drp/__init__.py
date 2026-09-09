"""Drone-Based Delivery Optimization.

A capacitated drone routing problem with load-dependent energy, battery and
payload limits, and no-fly zones -- with an exact method, three metaheuristics,
a reproducible benchmark generator, and an experiment harness.

Typical use::

    from drp import default_benchmark_suite, solve_one

    inst = default_benchmark_suite()[0]
    res = solve_one(inst, "alns", time_limit=5)
    print(res.energy, res.feasible)
"""
from drp.core import (DRPInstance, Solution, evaluate, feasibility_certificate,
                      is_feasible, route_energy, route_weight, total_energy)
from drp.eval import (METHODS, ResultStore, instance_rows, method_summary,
                      run_study, solve_one)
from drp.exact import BnBResult, solve_bnb, solve_formulation2
from drp.instances import (default_benchmark_suite, generate_instance,
                           generate_zone_instance, load_instance,
                           load_solution, save_instance, save_solution,
                           zone_benchmark_suite)
from drp.meta import (best_construction, nearest_neighbour_routes,
                      savings_construction, solve_alns, solve_ga, solve_sa,
                      split, warm_start_tour)

__version__ = "2.0.0"

__all__ = [
    "DRPInstance", "Solution", "route_energy", "route_weight", "total_energy",
    "is_feasible", "evaluate", "feasibility_certificate",
    "generate_instance", "generate_zone_instance", "default_benchmark_suite",
    "zone_benchmark_suite", "save_instance", "load_instance", "save_solution",
    "load_solution",
    "nearest_neighbour_routes", "savings_construction", "best_construction",
    "warm_start_tour", "split", "solve_ga", "solve_sa", "solve_alns",
    "solve_bnb", "BnBResult", "solve_formulation2",
    "solve_one", "run_study", "ResultStore", "instance_rows", "method_summary",
    "METHODS", "__version__",
]
