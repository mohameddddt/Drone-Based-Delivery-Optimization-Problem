"""Generate all figures for report/report.tex.

Reads the tables written by `run_experiments.py` so the figures always describe
the same run as the report's numbers. The convergence, route and playback
figures need live solver runs; those import from the `drp` package, so there is
no second copy of any algorithm anywhere in the repository.

Usage
-----
    python run_experiments.py      # first: fill the results store
    python generate_figures.py     # then: render the figures

Figures
-------
    fig_comparison.png    best energy by method and instance
    fig_gap.png           gap to reference (proven optimum where known)
    fig_bnb_dual.png      B&B incumbent vs dual bound -- what §5.1 bought us
    fig_runtime.png       runtime vs instance size
    fig_convergence.png   GA vs SA vs ALNS on a medium instance
    fig_routes.png        the flown routes of a solution
    fig_zones.png         detour routing around polygonal no-fly zones
    playback.gif          animated fleet playback (with --animate)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from drp.eval.runner import solve_one
from drp.instances import default_benchmark_suite, generate_zone_instance
from drp.meta.construct import best_construction, warm_start_tour
from drp.meta.alns import solve_alns
from drp.meta.ga import solve_ga
from drp.meta.sa import solve_sa
from drp.viz.static import (plot_bnb_dual_gap, plot_convergence,
                            plot_gap_to_reference, plot_method_comparison,
                            plot_routes, plot_runtime)

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"

METHODS = ("greedy", "bnb", "ga", "sa", "alns")


def load_results():
    path = RESULTS / "results.json"
    if not path.exists():
        raise SystemExit(
            "results/results.json not found -- run `python run_experiments.py` first.")
    return json.loads(path.read_text(encoding="utf-8"))


def figures_from_tables(recs) -> None:
    present = [m for m in METHODS if any(r.get(f"{m}_best") is not None for r in recs)]
    print(f"saved {plot_method_comparison(recs, present, RESULTS / 'fig_comparison.png')}")
    print(f"saved {plot_gap_to_reference(recs, [m for m in present if m != 'greedy'], RESULTS / 'fig_gap.png')}")
    print(f"saved {plot_bnb_dual_gap(recs, RESULTS / 'fig_bnb_dual.png')}")
    print(f"saved {plot_runtime(recs, present, RESULTS / 'fig_runtime.png')}")


def figure_convergence(time_limit: float) -> None:
    print(f"running GA, SA and ALNS for the convergence figure "
          f"(~{3 * time_limit:.0f}s)...")
    inst = [i for i in default_benchmark_suite() if i.name == "M3_n18_k5"][0]
    wt = warm_start_tour(inst)
    hist = {
        "ga": solve_ga(inst, seed=1, time_limit=time_limit, warm_tours=[wt]).history,
        "sa": solve_sa(inst, seed=1, time_limit=time_limit, warm_tour=wt).history,
        "alns": solve_alns(inst, seed=1, time_limit=time_limit, warm_tour=wt).history,
    }
    print(f"saved {plot_convergence(hist, RESULTS / 'fig_convergence.png', title=f'Convergence on {inst.name} ($n=18$, $K=5$)')}")


def figure_routes(time_limit: float) -> None:
    print(f"running ALNS for the routes figure (~{time_limit:.0f}s)...")
    inst = [i for i in default_benchmark_suite() if i.name == "S6_n10_k3"][0]
    res = solve_one(inst, "alns", seed=1, time_limit=time_limit)
    print(f"saved {plot_routes(inst, res.solution, RESULTS / 'fig_routes.png', title=f'ALNS solution -- {inst.name} ($E={res.energy:.0f}$)')}")


def figure_zones(time_limit: float, animate: bool) -> None:
    """The §4.1 figure: routes bending around polygonal no-fly zones."""
    print(f"running ALNS on a zone instance (~{time_limit:.0f}s)...")
    inst = generate_zone_instance("zones_n14_k4", 14, 4, 7, n_zones=3)
    res = solve_one(inst, "alns", seed=1, time_limit=time_limit)
    print(f"saved {plot_routes(inst, res.solution, RESULTS / 'fig_zones.png', title=f'Detour routing around no-fly zones ($E={res.energy:.0f}$)')}")

    if animate:
        from drp.viz.animate import animate_routes
        print("rendering the animated playback (this takes a moment)...")
        print(f"saved {animate_routes(inst, res.solution, RESULTS / 'playback.gif')}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--time-limit", type=float, default=6.0,
                    help="seconds per live solver run (default 6)")
    ap.add_argument("--animate", action="store_true",
                    help="also render the animated fleet playback (§2.2)")
    args = ap.parse_args()

    RESULTS.mkdir(exist_ok=True)
    figures_from_tables(load_results())
    figure_convergence(args.time_limit)
    figure_routes(args.time_limit)
    figure_zones(args.time_limit, args.animate)
    print("\nall figures saved to results/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
