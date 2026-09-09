"""Command-line interface (roadmap §1.3).

    drp generate --n 40 --drones 8 --zones 3 --seed 7 -o inst.json
    drp solve    inst.json --method alns --time 60 --seed 1 -o sol.json
    drp compare  inst.json --methods bnb,ga,sa,alns --seeds 1-10 --time 30
    drp show     sol.json --instance inst.json -o routes.png
    drp export   sol.json --instance inst.json --format geojson -o routes.geojson
    drp bench    --suite default --time 5 --seeds 1-5
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from drp.core import is_feasible, total_energy
from drp.eval.metrics import instance_rows, method_summary
from drp.eval.runner import METHODS, run_study, solve_one
from drp.eval.store import ResultStore
from drp.instances import (default_benchmark_suite, generate_instance,
                           generate_zone_instance, load_instance,
                           load_solution, save_instance, save_solution,
                           solution_to_csv, solution_to_geojson,
                           zone_benchmark_suite)


def parse_seeds(spec: str) -> List[int]:
    """Accept ``1-10``, ``1,3,5`` or a single number."""
    spec = spec.strip()
    if "-" in spec and "," not in spec:
        lo, hi = spec.split("-", 1)
        return list(range(int(lo), int(hi) + 1))
    return [int(x) for x in spec.split(",") if x.strip()]


# ---------------------------------------------------------------------------
def cmd_generate(args) -> int:
    if args.zones > 0:
        inst = generate_zone_instance(args.name, args.n, args.drones, args.seed,
                                      n_zones=args.zones)
    else:
        inst = generate_instance(args.name, args.n, args.drones, args.seed,
                                 nofly_fraction=args.nofly)
    out = Path(args.output)
    save_instance(inst, out)
    print(f"wrote {out}  (n={inst.n_customers}, K={inst.n_drones}, "
          f"payload={inst.payload:.1f}, battery={inst.battery:.1f}, "
          f"zones={len(inst.nofly_zones)}, nofly_edges={len(inst.nofly_edges)})")
    return 0


def cmd_solve(args) -> int:
    inst = load_instance(args.instance)
    res = solve_one(inst, args.method, seed=args.seed, time_limit=args.time)

    if res.solution is None:
        print(f"{args.method}: no feasible solution found", file=sys.stderr)
        return 1

    ok, reason = is_feasible(inst, res.solution)
    print(f"instance : {inst.name}  (n={inst.n_customers}, K={inst.n_drones})")
    print(f"method   : {args.method}")
    print(f"energy   : {res.energy:.2f}")
    if res.dual_bound is not None:
        if res.optimal:
            print("status   : proven optimal")
        else:
            gap = 100.0 * (res.energy - res.dual_bound) / res.energy
            print(f"status   : timed out -- lower bound {res.dual_bound:.2f}, "
                  f"gap {gap:.2f}%")
    print(f"feasible : {ok} ({reason})")
    print(f"time     : {res.wall_time:.2f}s")
    for k, r in enumerate(res.solution.used_routes()):
        print(f"  drone {k + 1}: {r}")

    if args.output:
        p = save_solution(inst, res.solution, args.output, method=args.method,
                          meta={"seed": args.seed, "time_limit": args.time,
                                "wall_time": res.wall_time,
                                "dual_bound": res.dual_bound,
                                "optimal": res.optimal})
        print(f"wrote {p}")
    return 0


def cmd_compare(args) -> int:
    inst = load_instance(args.instance)
    methods = [m.strip() for m in args.methods.split(",") if m.strip()]
    seeds = parse_seeds(args.seeds)

    store = run_study([inst], methods=methods, seeds=seeds,
                      time_limit=args.time, bnb_time_limit=args.time,
                      store=ResultStore(args.store))
    rows = store.rows(store.latest_group())

    print(f"\n{inst.name}: n={inst.n_customers}, K={inst.n_drones}, "
          f"{len(seeds)} seed(s), {args.time}s budget\n")
    print(f"{'method':10s} {'best':>10s} {'mean':>10s} {'time(s)':>9s}")
    print("-" * 42)
    for rec in instance_rows(rows):
        for m in methods:
            best = rec.get(f"{m}_best")
            if best is None:
                print(f"{m:10s} {'infeasible':>10s}")
                continue
            print(f"{m:10s} {best:10.1f} {rec.get(f'{m}_mean', best):10.1f} "
                  f"{rec.get(f'{m}_time', 0.0):9.2f}")
    store.close()
    return 0


def cmd_bench(args) -> int:
    suite = (zone_benchmark_suite() if args.suite == "zones"
             else default_benchmark_suite())
    methods = [m.strip() for m in args.methods.split(",") if m.strip()]
    seeds = parse_seeds(args.seeds)

    store = run_study(suite, methods=methods, seeds=seeds,
                      time_limit=args.time, bnb_time_limit=args.bnb_time,
                      store=ResultStore(args.store),
                      progress=(print if args.verbose else None))
    group = store.latest_group()
    rows = store.rows(group)

    print(f"\nrun group: {group}\n")
    print(f"{'method':22s} {'avg energy':>11s} {'avg time':>9s} {'optima':>8s}")
    print("-" * 54)
    for s in method_summary(rows):
        print(f"{s['method']:22s} {s['avg_energy'] or 0:11.1f} "
              f"{s['avg_time_s']:9.2f} "
              f"{s['optima_found']:>4d}/{s['n_proven']}")
    print(f"\nstored in {args.store}")
    store.close()
    return 0


def cmd_show(args) -> int:
    from drp.viz.static import plot_routes

    inst = load_instance(args.instance)
    sol = load_solution(args.solution, n_drones=inst.n_drones)
    out = plot_routes(inst, sol, args.output,
                      title=f"{inst.name} (E={total_energy(inst, sol):.0f})")
    print(f"wrote {out}")
    if args.animate:
        from drp.viz.animate import animate_routes
        gif = animate_routes(inst, sol, args.animate)
        print(f"wrote {gif}")
    return 0


def cmd_export(args) -> int:
    inst = load_instance(args.instance)
    sol = load_solution(args.solution, n_drones=inst.n_drones)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    if args.format == "geojson":
        out.write_text(json.dumps(solution_to_geojson(inst, sol), indent=2),
                       encoding="utf-8")
    elif args.format == "csv":
        out.write_text(solution_to_csv(inst, sol), encoding="utf-8")
    else:
        raise SystemExit(f"unknown format {args.format!r}")
    print(f"wrote {out}")
    return 0


# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="drp", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="create a benchmark instance")
    g.add_argument("--name", default="instance")
    g.add_argument("--n", type=int, required=True, help="number of customers")
    g.add_argument("--drones", type=int, required=True)
    g.add_argument("--seed", type=int, default=1)
    g.add_argument("--nofly", type=float, default=0.0,
                   help="fraction of longest edges to forbid (edge model)")
    g.add_argument("--zones", type=int, default=0,
                   help="number of polygonal no-fly zones (detour model)")
    g.add_argument("-o", "--output", default="instance.json")
    g.set_defaults(func=cmd_generate)

    s = sub.add_parser("solve", help="solve one instance with one method")
    s.add_argument("instance")
    s.add_argument("--method", default="alns", choices=list(METHODS))
    s.add_argument("--time", type=float, default=10.0, help="seconds")
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("-o", "--output")
    s.set_defaults(func=cmd_solve)

    c = sub.add_parser("compare", help="compare methods on one instance")
    c.add_argument("instance")
    c.add_argument("--methods", default="greedy,bnb,ga,sa,alns")
    c.add_argument("--seeds", default="1-3")
    c.add_argument("--time", type=float, default=5.0)
    c.add_argument("--store", default="results/runs.db")
    c.set_defaults(func=cmd_compare)

    b = sub.add_parser("bench", help="run a whole benchmark suite")
    b.add_argument("--suite", default="default", choices=["default", "zones"])
    b.add_argument("--methods", default="greedy,bnb,ga,sa,alns")
    b.add_argument("--seeds", default="1-5")
    b.add_argument("--time", type=float, default=5.0,
                   help="seconds per metaheuristic seed")
    b.add_argument("--bnb-time", type=float, default=20.0)
    b.add_argument("--store", default="results/runs.db")
    b.add_argument("-v", "--verbose", action="store_true")
    b.set_defaults(func=cmd_bench)

    sh = sub.add_parser("show", help="plot a solution")
    sh.add_argument("solution")
    sh.add_argument("--instance", required=True)
    sh.add_argument("-o", "--output", default="routes.png")
    sh.add_argument("--animate", metavar="GIF",
                    help="also write an animated playback to this path")
    sh.set_defaults(func=cmd_show)

    e = sub.add_parser("export", help="export a solution for other tools")
    e.add_argument("solution")
    e.add_argument("--instance", required=True)
    e.add_argument("--format", default="geojson", choices=["geojson", "csv"])
    e.add_argument("-o", "--output", required=True)
    e.set_defaults(func=cmd_export)

    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
