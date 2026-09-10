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
    fig_comparison        best energy by method and instance
    fig_gap               gap to reference (proven optimum where known)
    fig_bnb_dual          B&B incumbent vs dual bound -- what §5.1 bought us
    fig_runtime           runtime vs instance size
    fig_convergence       GA vs SA vs ALNS on a medium instance
    fig_routes            the flown routes of a solution
    fig_zones             detour routing around polygonal no-fly zones
    fig_theme             the route palette under each kind of colour vision
    playback.gif          animated fleet playback (with --animate)

Formats (roadmap §2.5)
----------------------
Each figure is written **twice**, as ``.pdf`` and ``.png``; ``--formats``
changes that.

PDF, not SVG, is the vector format the report consumes. ``report/report.tex``
is built with pdflatex, which embeds a PDF directly, while an SVG needs
``--shell-escape`` and an Inkscape on the build machine -- a dependency the
report does not otherwise have. The ``\\includegraphics`` calls are now written
without an extension, so LaTeX takes the PDF and falls back to the PNG if the
vector file is missing.

PNG stays because plenty of things that are not LaTeX read these files: the
README, the CI artifact upload, anything wanting a thumbnail. It costs about a
second per figure.

SVG is available -- ``--formats svg``, or ``-o something.svg`` on ``drp show``
-- for slides and the web. It is not written by default because nothing in the
repository consumes it.

TikZ was considered and rejected, and this is the place to say so rather than
half-adding it. Over PDF it buys exactly one thing: figure text set in the
document's own font, at the document's own size, by the same typesetter. It
costs a matplotlib-to-TikZ dependency, a build that can now fail inside LaTeX
rather than inside Python, and tens of thousands of generated lines of .tex per
data-heavy figure -- ``fig_comparison`` alone draws 60 bars. The font argument
is weaker here than it sounds, too, because these figures are placed at
``width=\\textwidth`` where matplotlib's 11 pt already lands close to the body
text. If the report ever does need figure text to match exactly, the cheap half
of that is matplotlib's own ``pgf`` backend, which needs no new Python
dependency; try it before reaching for TikZ.
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
                            plot_routes, plot_runtime, plot_theme_swatches)

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"

METHODS = ("greedy", "bnb", "ga", "sa", "alns")
#: Written for every figure. PDF is what report.tex consumes; PNG is what
#: everything that is not LaTeX consumes. See the module docstring.
DEFAULT_FORMATS = ("pdf", "png")


#: The fraction of `	extwidth` each figure is placed at in report.tex. The
#: plot functions use it to size type and strokes so they land readable *on the
#: page* -- see `drp.viz.static.report_typography`. Keep this in step with the
#: `\includegraphics[width=...]` calls; a figure listed at the wrong width
#: gets type that is merely differently wrong.
PLACED_AT = {
    "fig_comparison": 1.00,
    "fig_gap": 1.00,
    "fig_bnb_dual": 1.00,
    "fig_runtime": 1.00,
    "fig_convergence": 0.90,
    "fig_routes": 0.65,
    "fig_zones": 0.72,
}


def _save_all(plot, stem, formats, *args, **kwargs):
    """Call `plot(*args, path, **kwargs)` once per format and report each.

    The figure is drawn once per format, which is milliseconds for the four
    table-driven figures. The three that need a live solver run compute the
    run once and re-plot the *result*, so no solver ever runs twice.
    """
    if stem in PLACED_AT:
        kwargs.setdefault("placed_at", PLACED_AT[stem])
    for fmt in formats:
        path = RESULTS / f"{stem}.{fmt.lstrip('.')}"
        print(f"saved {plot(*args, path, **kwargs)}")


def load_results():
    path = RESULTS / "results.json"
    if not path.exists():
        raise SystemExit(
            "results/results.json not found -- run `python run_experiments.py` first.")
    return json.loads(path.read_text(encoding="utf-8"))


def figures_from_tables(recs, formats) -> None:
    present = [m for m in METHODS if any(r.get(f"{m}_best") is not None for r in recs)]
    _save_all(plot_method_comparison, "fig_comparison", formats, recs, present)
    _save_all(plot_gap_to_reference, "fig_gap", formats, recs,
              [m for m in present if m != "greedy"])
    _save_all(plot_bnb_dual_gap, "fig_bnb_dual", formats, recs)
    _save_all(plot_runtime, "fig_runtime", formats, recs, present)


def figure_convergence(time_limit: float, formats) -> None:
    print(f"running GA, SA and ALNS for the convergence figure "
          f"(~{3 * time_limit:.0f}s)...")
    inst = [i for i in default_benchmark_suite() if i.name == "M3_n18_k5"][0]
    wt = warm_start_tour(inst)
    hist = {
        "ga": solve_ga(inst, seed=1, time_limit=time_limit, warm_tours=[wt]).history,
        "sa": solve_sa(inst, seed=1, time_limit=time_limit, warm_tour=wt).history,
        "alns": solve_alns(inst, seed=1, time_limit=time_limit, warm_tour=wt).history,
    }
    _save_all(plot_convergence, "fig_convergence", formats, hist,
              title=f"Convergence on {inst.name} ($n=18$, $K=5$)")


def figure_routes(time_limit: float, formats) -> None:
    print(f"running ALNS for the routes figure (~{time_limit:.0f}s)...")
    inst = [i for i in default_benchmark_suite() if i.name == "S6_n10_k3"][0]
    res = solve_one(inst, "alns", seed=1, time_limit=time_limit)
    _save_all(plot_routes, "fig_routes", formats, inst, res.solution,
              title=f"ALNS solution -- {inst.name} ($E={res.energy:.0f}$)")


def figure_zones(time_limit: float, animate: bool, formats) -> None:
    """The §4.1 figure: routes bending around polygonal no-fly zones."""
    print(f"running ALNS on a zone instance (~{time_limit:.0f}s)...")
    inst = generate_zone_instance("zones_n14_k4", 14, 4, 7, n_zones=3)
    res = solve_one(inst, "alns", seed=1, time_limit=time_limit)
    _save_all(plot_routes, "fig_zones", formats, inst, res.solution,
              title=f"Detour routing around no-fly zones ($E={res.energy:.0f}$)")

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
    ap.add_argument("--formats", default=",".join(DEFAULT_FORMATS),
                    help=("comma-separated output formats; the extension picks "
                          f"the backend (default {','.join(DEFAULT_FORMATS)})"))
    ap.add_argument("--theme", default=None,
                    help="colour theme: safe (the default) or chart")
    args = ap.parse_args()

    if args.theme:
        from drp.viz.theme import use_theme
        use_theme(args.theme)
    formats = [f.strip() for f in args.formats.split(",") if f.strip()]

    RESULTS.mkdir(exist_ok=True)
    figures_from_tables(load_results(), formats)
    figure_convergence(args.time_limit, formats)
    figure_routes(args.time_limit, formats)
    figure_zones(args.time_limit, args.animate, formats)
    # Not a result: the evidence for the theme. See `drp/viz/theme.py`.
    _save_all(plot_theme_swatches, "fig_theme", formats)
    print("\nall figures saved to results/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
