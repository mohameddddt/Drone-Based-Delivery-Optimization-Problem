"""Command-line interface (roadmap §1.3).

    drp generate --n 40 --drones 8 --zones 3 --seed 7 -o inst.json
    drp solve    inst.json --method alns --time 60 --seed 1 -o sol.json
    drp compare  inst.json --methods bnb,ga,sa,alns --seeds 1-10 --time 30
    drp show     sol.json --instance inst.json -o routes.svg
    drp tree     inst.json --time 20 -o tree.html
    drp dash     inst.json --methods ga,sa,alns --time 5 -o dash.html
    drp export   sol.json --instance inst.json --format geojson -o routes.geojson
    drp bench    --suite default --time 5 --seeds 1-5

`docs/VISUALISATION.md` is the runnable guide to every view `show` and `tree`
produce.

Every view-producing subcommand takes ``--theme``. The default, ``safe``, is
the colour-blind-safe theme (roadmap 2.5); ``--theme chart`` is the original
aeronautical-chart palette, kept so committed figures regenerate unchanged.
``DRP_VIZ_THEME`` sets the default for a shell.
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
    title = args.title or f"{inst.name} (E={total_energy(inst, sol):.0f})"
    out = plot_routes(inst, sol, args.output, title=title)
    print(f"wrote {out}")
    if args.animate:
        from drp.viz.animate import animate_routes
        gif = animate_routes(inst, sol, args.animate, frames=args.frames,
                             fps=args.fps, separation=args.separation,
                             title=args.title)
        print(f"wrote {gif}")
    if args.web:
        from drp.viz.webplayback import render_playback_html
        vision = None
        if args.vision:
            vision = _solver_vision(inst, sol, args)
        page = render_playback_html(inst, sol, args.web, title=args.title,
                                    separation=args.separation, vision=vision)
        print(f"wrote {page}")
        if vision is not None:
            print(f"  solver vision: {vision['matched']}/{vision['total']} route "
                  f"steps matched a node ({vision['exact']} exact) in a "
                  f"{vision['nodes_explored']}-node B&B search")
    return 0


def _solver_vision(inst, sol, args):
    """Run B&B with a trace so the replay can show what the search rejected.

    This is a *second* search, independent of whatever produced `sol` -- the
    replay says so on the page. Where the search never stood at a given point in
    a route there is simply no entry; nothing is synthesised to fill the gap.
    """
    from drp.exact.bnb import solve_bnb
    from drp.meta.construct import best_construction
    from drp.viz.treedata import build_vision_data

    res = solve_bnb(inst, time_limit=args.vision_time,
                    warm_start=best_construction(inst), trace=True,
                    trace_max_nodes=args.max_nodes)
    return build_vision_data(inst, sol, res)


def cmd_tree(args) -> int:
    """Run B&B with tracing on and render the search-tree explorer."""
    from drp.exact.bnb import solve_bnb
    from drp.meta.construct import best_construction
    from drp.viz.webtree import render_tree_html

    inst = load_instance(args.instance)
    warm = None if args.no_warm_start else best_construction(inst)
    res = solve_bnb(inst, time_limit=args.time, warm_start=warm, trace=True,
                    trace_max_nodes=args.max_nodes)

    print(f"instance : {inst.name}  (n={inst.n_customers}, K={inst.n_drones})")
    print(f"search   : {res.summary()}")
    print(f"trace    : {len(res.trace.nodes)} nodes recorded"
          + (f" (capped at {args.max_nodes}; the search itself ran on)"
             if res.trace.truncated else ""))

    page = render_tree_html(inst, res, args.output, title=args.title)
    print(f"wrote {page}")

    if args.solution and res.best_solution is not None:
        p = save_solution(inst, res.best_solution, args.solution, method="bnb",
                          meta={"time_limit": args.time,
                                "dual_bound": res.dual_bound,
                                "optimal": res.optimal,
                                "nodes_explored": res.nodes_explored})
        print(f"wrote {p}")
    return 0


def cmd_dash(args) -> int:
    """Run each metaheuristic with tracing on and render the convergence
    dashboard."""
    from drp.meta.alns import solve_alns
    from drp.meta.construct import best_construction
    from drp.meta.ga import solve_ga
    from drp.meta.sa import solve_sa
    from drp.viz.dashdata import MethodRun
    from drp.viz.webdash import render_dashboard_html

    inst = load_instance(args.instance)
    methods = [m.strip().lower() for m in args.methods.split(",") if m.strip()]
    unknown = [m for m in methods if m not in ("ga", "sa", "alns")]
    if unknown:
        raise SystemExit(f"dash supports ga, sa and alns; got {unknown}")

    ws = best_construction(inst)
    wt = ws.giant_tour() if ws else None
    runs = []
    for m in methods:
        common = dict(seed=args.seed, time_limit=args.time, trace=True,
                      trace_max_samples=args.max_samples)
        if m == "ga":
            r = solve_ga(inst, warm_tours=[wt] if wt else None, **common)
            steps, extra = r.generations, {"generations": r.generations}
        elif m == "sa":
            r = solve_sa(inst, warm_tour=wt, **common)
            steps = r.iterations
            extra = {"iterations": r.iterations, "accepted": r.accepted,
                     "accepted_uphill": r.accepted_uphill, "reheats": r.reheats}
        else:
            r = solve_alns(inst, warm_tour=wt, **common)
            steps = r.iterations
            extra = {"iterations": r.iterations,
                     "destroy_weights": r.destroy_weights,
                     "repair_weights": r.repair_weights}
        print(f"{m:5s}: E={r.best_energy:10.2f}  {steps:7d} steps  "
              f"{r.time:5.2f}s  {len(r.trace.samples)} samples"
              + (f" (every {r.trace.stride})" if r.trace.stride > 1 else ""))
        runs.append(MethodRun(m, r.trace, r.best_energy, r.time, args.seed,
                              solution=r.best_solution, extra=extra))

    reference, ref_label = None, ""
    if args.reference > 0:
        from drp.exact.bnb import solve_bnb
        b = solve_bnb(inst, time_limit=args.reference, warm_start=ws)
        if b.optimal:
            reference, ref_label = b.best_energy, "B&B optimum"
            print(f"bnb  : E={b.best_energy:10.2f}  proven optimal "
                  f"({b.nodes_explored} nodes, {b.time:.2f}s)")
        else:
            # An unproven incumbent is not a floor, and drawing it as one would
            # be a lie about what is known. Its dual bound genuinely is a floor.
            reference, ref_label = b.dual_bound, "B&B dual bound"
            print(f"bnb  : did not prove optimality in {args.reference}s; "
                  f"using its dual bound {b.dual_bound:.2f} as the floor")

    page = render_dashboard_html(inst, runs, args.output, reference=reference,
                                 reference_label=ref_label, title=args.title)
    print(f"wrote {page}")
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


def _add_theme(parser: argparse.ArgumentParser) -> None:
    """`--theme` for every subcommand that draws something.

    Declared per-subcommand rather than on the top-level parser so that
    `drp show --theme chart ...` works; a top-level-only option would have to
    be written before the subcommand name, which nobody does.
    """
    from drp.viz.theme import DEFAULT_THEME, theme_names
    parser.add_argument("--theme", default=None, choices=theme_names(),
                        help=(f"colour theme (default {DEFAULT_THEME}; "
                              f"$DRP_VIZ_THEME overrides that, --theme "
                              f"overrides both)"))


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
    sh.add_argument("-o", "--output", default="routes.png",
                    help=("static plot; the extension picks the format -- .png "
                          "for a raster, .svg/.pdf/.eps for vector geometry"))
    sh.add_argument("--animate", metavar="GIF",
                    help="also write an animated playback to this path")
    sh.add_argument("--web", metavar="HTML",
                    help="also write an interactive GSAP flight-playback page to this path")
    sh.add_argument("--title", help="title for the plot, the GIF and the web page")
    sh.add_argument("--frames", type=int, default=160,
                    help="animation frames (--animate only)")
    sh.add_argument("--fps", type=int, default=20,
                    help="animation frames per second (--animate only)")
    sh.add_argument("--separation", type=float,
                    help="conflict distance for --animate and --web "
                         "(default: 3%% of the field span)")
    sh.add_argument("--vision", action="store_true",
                    help="run a traced B&B and show, in --web, the partial "
                         "routes the search considered and rejected")
    sh.add_argument("--vision-time", type=float, default=10.0,
                    help="seconds for the --vision B&B search")
    _add_theme(sh)
    sh.add_argument("--max-nodes", type=int, default=20000,
                    help="cap on trace records for --vision")
    sh.set_defaults(func=cmd_show)

    tr = sub.add_parser("tree", help="explore the B&B search tree in a browser")
    tr.add_argument("instance")
    tr.add_argument("--time", type=float, default=20.0,
                    help="seconds of search budget")
    tr.add_argument("-o", "--output", default="tree.html")
    tr.add_argument("--max-nodes", type=int, default=4000,
                    help="cap on recorded nodes; the search is never truncated")
    tr.add_argument("--title", help="title for the page")
    tr.add_argument("--solution", metavar="JSON",
                    help="also write the solution B&B found to this path")
    _add_theme(tr)
    tr.add_argument("--no-warm-start", action="store_true",
                    help="start with no incumbent, so the tree shows the search "
                         "finding its first solution")
    tr.set_defaults(func=cmd_tree)

    da = sub.add_parser("dash", help="convergence dashboard for the metaheuristics")
    da.add_argument("instance")
    da.add_argument("--methods", default="ga,sa,alns")
    da.add_argument("--time", type=float, default=5.0,
                    help="seconds per method")
    da.add_argument("--seed", type=int, default=1)
    da.add_argument("-o", "--output", default="dash.html")
    da.add_argument("--max-samples", type=int, default=3000,
                    help="samples kept per method; the run is decimated "
                         "uniformly, never truncated")
    da.add_argument("--reference", type=float, default=0.0, metavar="SECONDS",
                    help="also run B&B for this long and draw its optimum "
                         "(or, failing that, its dual bound) as a floor")
    _add_theme(da)
    da.add_argument("--title", help="title for the page")
    da.set_defaults(func=cmd_dash)

    e = sub.add_parser("export", help="export a solution for other tools")
    e.add_argument("solution")
    e.add_argument("--instance", required=True)
    e.add_argument("--format", default="geojson", choices=["geojson", "csv"])
    e.add_argument("-o", "--output", required=True)
    e.set_defaults(func=cmd_export)

    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    theme = getattr(args, "theme", None)
    if theme:
        from drp.viz.theme import use_theme
        use_theme(theme)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
