from __future__ import annotations

import csv
from pathlib import Path

from .exact import solve_branch_and_bound
from .ga import solve_genetic
from .io import load_instance, save_solution
from .models import Instance, Solution
from .sa import solve_simulated_annealing


def run_experiment(
    instances_root: str | Path,
    output_root: str | Path,
    seed: int = 2026,
    exact_time_limit: float = 60.0,
) -> list[dict[str, str]]:
    instances_root = Path(instances_root)
    output_root = Path(output_root)
    solutions_root = output_root / "solutions"
    output_root.mkdir(parents=True, exist_ok=True)
    solutions_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    folders = sorted(path for path in instances_root.iterdir() if path.is_dir())
    for index, folder in enumerate(folders, start=1):
        instance = load_instance(folder)
        solutions = [
            solve_branch_and_bound(instance, time_limit=exact_time_limit),
            solve_genetic(instance, seed=seed + index),
            solve_simulated_annealing(instance, seed=seed + 1000 + index),
        ]
        best_exact = next((solution for solution in solutions if solution.method == "Branch and Bound"), None)
        for solution in solutions:
            if best_exact and best_exact.feasible and solution.feasible:
                reference = best_exact.cost
                if reference > 0:
                    solution.gap_percent = max(0.0, (solution.cost - reference) / reference * 100.0)
            save_solution(
                instance,
                solution,
                solutions_root / f"{instance.name}_{slug(solution.method)}.json",
            )
            rows.append(result_row(instance, solution))
    write_results(output_root / "experiment_results.csv", rows)
    write_summary(output_root / "summary.csv", rows)
    return rows


def result_row(instance: Instance, solution: Solution) -> dict[str, str]:
    return {
        "instance": instance.name,
        "customers": str(instance.n_customers),
        "drones": str(instance.n_drones),
        "method": solution.method,
        "feasible": str(solution.feasible),
        "optimal": str(solution.optimal),
        "cost": f"{solution.cost:.6f}",
        "distance": f"{solution.total_distance:.6f}",
        "routes": str(solution.route_count),
        "runtime_sec": f"{solution.runtime_sec:.6f}",
        "iterations": str(solution.iterations),
        "lower_bound": "" if solution.lower_bound is None else f"{solution.lower_bound:.6f}",
        "gap_percent": "" if solution.gap_percent is None else f"{solution.gap_percent:.6f}",
    }


def write_results(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, rows: list[dict[str, str]]) -> None:
    methods = sorted({row["method"] for row in rows})
    summary: list[dict[str, str]] = []
    for method in methods:
        group = [row for row in rows if row["method"] == method and row["feasible"] == "True"]
        if not group:
            continue
        costs = [float(row["cost"]) for row in group]
        runtimes = [float(row["runtime_sec"]) for row in group]
        gaps = [float(row["gap_percent"]) for row in group if row["gap_percent"]]
        summary.append(
            {
                "method": method,
                "feasible_runs": str(len(group)),
                "average_cost": f"{sum(costs) / len(costs):.6f}",
                "average_runtime_sec": f"{sum(runtimes) / len(runtimes):.6f}",
                "average_gap_percent": "" if not gaps else f"{sum(gaps) / len(gaps):.6f}",
            }
        )
    if summary:
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=list(summary[0]))
            writer.writeheader()
            writer.writerows(summary)


def slug(value: str) -> str:
    return value.lower().replace(" ", "_")
