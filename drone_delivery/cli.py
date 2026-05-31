from __future__ import annotations

import argparse
from pathlib import Path

from .exact import solve_branch_and_bound
from .experiment import run_experiment
from .ga import solve_genetic
from .generator import generate_benchmark
from .io import load_instance, save_solution
from .sa import solve_simulated_annealing


def main() -> None:
    parser = argparse.ArgumentParser(prog="drone-delivery")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate")
    generate.add_argument("--output", default="data/instances")
    generate.add_argument("--count", type=int, default=10)
    generate.add_argument("--seed", type=int, default=2026)

    solve = subparsers.add_parser("solve")
    solve.add_argument("instance")
    solve.add_argument("--method", choices=["exact", "ga", "sa", "all"], default="all")
    solve.add_argument("--output", default="results/manual")
    solve.add_argument("--seed", type=int, default=2026)
    solve.add_argument("--time-limit", type=float, default=60.0)

    experiment = subparsers.add_parser("experiment")
    experiment.add_argument("--instances", default="data/instances")
    experiment.add_argument("--output", default="results")
    experiment.add_argument("--seed", type=int, default=2026)
    experiment.add_argument("--time-limit", type=float, default=60.0)

    args = parser.parse_args()
    if args.command == "generate":
        paths = generate_benchmark(args.output, count=args.count, seed=args.seed)
        print(f"generated {len(paths)} instances in {Path(args.output)}")
    elif args.command == "solve":
        instance = load_instance(args.instance)
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        methods = ["exact", "ga", "sa"] if args.method == "all" else [args.method]
        for method in methods:
            solution = run_method(instance, method, args.seed, args.time_limit)
            save_solution(instance, solution, output / f"{instance.name}_{method}.json")
            status = "optimal" if solution.optimal else "feasible" if solution.feasible else "infeasible"
            print(
                f"{method}: {status}, cost={solution.cost:.3f}, "
                f"routes={solution.route_count}, time={solution.runtime_sec:.3f}s"
            )
    elif args.command == "experiment":
        rows = run_experiment(args.instances, args.output, seed=args.seed, exact_time_limit=args.time_limit)
        print(f"wrote {len(rows)} result rows to {Path(args.output)}")


def run_method(instance, method: str, seed: int, time_limit: float):
    if method == "exact":
        return solve_branch_and_bound(instance, time_limit=time_limit)
    if method == "ga":
        return solve_genetic(instance, seed=seed)
    if method == "sa":
        return solve_simulated_annealing(instance, seed=seed)
    raise ValueError(method)


if __name__ == "__main__":
    main()
