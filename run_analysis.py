r"""Roadmap §6, the profiling half, over any stored study.

`run_experiments.py` produces the runs and the significance tests. This reads a
run group back out of a results store -- no re-solving -- and adds what a
p-value cannot say: performance profiles, the ECDF of solution quality,
anytime curves with the primal integral, time-to-target distributions, and the
correlation of instance structure with how far each method finished from the
reference.

Usage
-----
    python run_analysis.py --suite default
    python run_analysis.py --suite geo
    python run_analysis.py --suite cvrplib          # gaps to published optima
    python run_analysis.py --suite solomon --group run_20260911_004351
    python run_analysis.py --store results/ablation_runs.db --suite default --no-hardness

Anytime and time-to-target need the per-run trajectories that runs record from
roadmap §6 onwards; for a group stored before that, those two sections report
zero runs rather than inventing a curve.

Outputs (``<tag>`` is the suite name unless ``--tag`` says otherwise)
-------
    results/analysis/<tag>.json               every number below
    results/analysis/<tag>_profile.{pdf,png}  Dolan-Moré performance profile
    results/analysis/<tag>_ecdf.{pdf,png}     per-run gap distribution
    results/analysis/<tag>_anytime.{pdf,png}  mean gap over time (if trajectories)
    results/analysis/<tag>_ttt.{pdf,png}      time-to-target ECDF (if trajectories)
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from drp.eval.profiles import (anytime_curves, hardness_correlation, instance_features,
                               mean_gap_by_instance, performance_profile,
                               quality_ecdf, reference_values, ttt_ecdf)
from drp.eval.store import ResultStore

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results" / "analysis"


def _jsonable(obj: Any) -> Any:
    """JSON has no Infinity or NaN; say what they meant instead."""
    if isinstance(obj, float):
        if math.isnan(obj):
            return None
        if math.isinf(obj):
            return "inf" if obj > 0 else "-inf"
        return obj
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


def load_instances(suite: str, names: List[str], rows: List[Dict],
                   benchmark_dir: Optional[str]) -> Tuple[Dict[str, Any], Dict[str, float]]:
    """The instance objects behind a group's rows, and any published optima."""
    from drp.instances import (benchmark_directory, default_benchmark_suite,
                               geo_benchmark_suite, zone_benchmark_suite)

    published: Dict[str, float] = {}
    if suite in ("cvrplib", "solomon"):
        root = Path(benchmark_dir or ("data/CVRPLIB" if suite == "cvrplib" else "data/Solomon"))
        if not root.exists():
            raise SystemExit(f"{root} does not exist; the {suite} files are not committed.")
        kwargs: Dict[str, Any] = {}
        if suite == "solomon":
            sizes = {r["n"] for r in rows}
            if len(sizes) != 1:
                raise SystemExit(f"group mixes Solomon sizes {sorted(sizes)}; pass one group")
            n = sizes.pop()
            # A truncated import is named "C101-25"; a whole file keeps "C101".
            if any(name.endswith(f"-{n}") for name in names):
                kwargs["n_customers"] = n
        imported = benchmark_directory(root, pattern="*.vrp" if suite == "cvrplib" else "*.txt",
                                       fmt=suite, **kwargs)
        insts = {imp.instance.name: imp.instance for imp in imported}
        if suite == "cvrplib":
            # Solomon's published values are VRPTW distances; our import drops
            # the windows, so they are not a reference for this problem.
            published = {imp.instance.name: imp.best_known for imp in imported
                         if imp.best_known is not None and imp.best_known_kind == "optimal"}
    else:
        builders = {"default": default_benchmark_suite, "geo": geo_benchmark_suite,
                    "zones": zone_benchmark_suite}
        insts = {i.name: i for i in builders[suite]()}
    missing = [n for n in names if n not in insts]
    if missing:
        raise SystemExit(f"instances in the group but not in the {suite} suite: {missing[:5]}")
    return {n: insts[n] for n in names}, {n: v for n, v in published.items() if n in names}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suite", default="default",
                    choices=["default", "zones", "geo", "cvrplib", "solomon"])
    ap.add_argument("--store", help="default: the suite's own store, as run_experiments.py")
    ap.add_argument("--group", help="run group (default: the store's latest)")
    ap.add_argument("--tag", help="output name (default: the suite name)")
    ap.add_argument("--methods", help="comma-separated subset, in legend order")
    ap.add_argument("--benchmark-dir")
    ap.add_argument("--eps", type=float, default=1.0,
                    help="time-to-target tolerance, %% above the reference (default 1)")
    ap.add_argument("--no-hardness", action="store_true",
                    help="skip the instance features (they need the instances)")
    ap.add_argument("--feature-samples", type=int, default=300,
                    help="random tours per instance for the Split-feasibility probe")
    ap.add_argument("--formats", default="pdf,png")
    args = ap.parse_args()

    store_path = args.store or ("results/runs.db" if args.suite == "default"
                                else f"results/{args.suite}_runs.db")
    store = ResultStore(store_path)
    group = args.group or store.latest_group()
    if group is None:
        raise SystemExit(f"{store_path} is empty")
    rows = store.rows(group)
    store.close()
    methods = ([m.strip() for m in args.methods.split(",")] if args.methods else
               [m for m in ("greedy", "bnb", "ga", "sa", "alns")
                if any(r["method"] == m for r in rows)]
               + sorted({r["method"] for r in rows} - {"greedy", "bnb", "ga", "sa", "alns"}))
    rows = [r for r in rows if r["method"] in methods]
    names = list(dict.fromkeys(r["instance"] for r in rows))
    tag = args.tag or args.suite
    print(f"{store_path} group {group}: {len(rows)} runs, {len(names)} instances, "
          f"methods {methods}")

    insts: Dict[str, Any] = {}
    published: Dict[str, float] = {}
    if not args.no_hardness or args.suite == "cvrplib":
        insts, published = load_instances(args.suite, names, rows, args.benchmark_dir)
    refs = reference_values(rows, published)
    ref_kind = "published optimum" if published else "proven B&B optimum, else best found"
    print(f"reference: {ref_kind} ({len(published)} published)")

    result: Dict[str, Any] = {"store": store_path, "group": group, "suite": args.suite,
                              "methods": methods, "reference": ref_kind, "refs": refs}

    # --- profiles and quality -------------------------------------------
    prof = performance_profile(rows, methods)
    prof_best = performance_profile(rows, methods, statistic="best")
    qual = quality_ecdf(rows, refs, methods)
    result["profile"] = {k: v for k, v in prof.items() if k != "ratios"}
    result["profile_ratios"] = prof["ratios"]
    result["profile_best_of_seeds"] = {"wins": prof_best["wins"]}
    result["quality"] = qual

    print(f"\nperformance profile ({prof['n_instances']} instances, mean over seeds)")
    print(f"  {'method':10s} {'wins':>6s} {'rho(1.01)':>10s} {'rho(1.05)':>10s} "
          f"{'rho(1.10)':>10s} {'worst':>8s} | {'median gap':>10s} {'p90':>8s} {'unsolved':>9s}")
    at = performance_profile(rows, methods, taus=[1.01, 1.05, 1.10])
    for m in methods:
        worst = max(r[m] for r in prof["ratios"].values()) if prof["ratios"] else math.nan
        q = qual[m]
        med = q["median"]
        print(f"  {m:10s} {prof['wins'][m]:6.0%} {at['rho'][m][0]:10.0%} "
              f"{at['rho'][m][1]:10.0%} {at['rho'][m][2]:10.0%} {worst:8.3f} | "
              f"{'inf' if med is None or math.isinf(med) else f'{med:9.2f}%':>10s} "
              f"{'--' if q['p90'] is None else f'{q['p90']:7.2f}%':>8s} "
              f"{q['unsolved']:4d}/{q['runs']:<4d}")

    # --- anytime ----------------------------------------------------------
    # B&B stores only its start and its end, so a curve for it would show its
    # final incumbent arriving at the moment it *stopped*, not when it was found.
    timed = [m for m in methods if m != "bnb"]
    curves = anytime_curves(rows, refs, timed)
    ttt = ttt_ecdf(rows, refs, timed, eps_pct=args.eps)
    result["anytime"] = curves
    result["ttt"] = ttt
    have_traj = any(d["runs"] for d in curves["methods"].values())
    if have_traj:
        print(f"\nanytime (runs with trajectories) and time to within {args.eps:g}%")
        for m in timed:
            d, t = curves["methods"][m], ttt["methods"][m]
            if not d["runs"]:
                continue
            med = t["median_reached_s"]
            print(f"  {m:10s} runs={d['runs']:4d}  primal integral="
                  f"{d['primal_integral']:.4f}  reached={t['success_rate']:.0%}  "
                  f"median time={'--' if med is None else f'{med:.3f}s'}")
    else:
        print("\nno anytime trajectories in this group (stored before roadmap section 6); "
              "anytime and time-to-target skipped")

    # --- hardness ---------------------------------------------------------
    if not args.no_hardness:
        t0 = time.time()
        feats = {n: instance_features(insts[n], samples=args.feature_samples)
                 for n in names}
        result["features"] = feats
        result["hardness"] = {}
        print(f"\ninstance features ({time.time() - t0:.1f}s); Spearman against mean gap, "
              "raw | controlling for n")
        for m in methods:
            gaps = mean_gap_by_instance(rows, refs, m)
            corr = hardness_correlation(feats, gaps)
            result["hardness"][m] = corr
            cells = []
            for c in corr:
                if c["rho"] is None:
                    continue
                pr = c["partial_rho"]
                cells.append(f"{c['feature']}={c['rho']:+.2f}"
                             + ("*" if c["p"] < 0.05 else "")
                             + ("" if pr is None else
                                f"|{pr:+.2f}" + ("*" if (c["partial_p"] or 1) < 0.05 else "")))
            print(f"  {m:8s} " + "  ".join(cells))
        print("  (* p < 0.05, uncorrected -- a screen for what to look at, not a finding)")

    # --- write --------------------------------------------------------------
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{tag}.json").write_text(json.dumps(_jsonable(result), indent=1), encoding="utf-8")
    print(f"\nwrote results/analysis/{tag}.json")

    from drp.viz.static import (plot_anytime, plot_performance_profile,
                                plot_quality_ecdf, plot_ttt)
    label = {"default": "synthetic suite", "geo": "Pontianak suite", "zones": "zone suite",
             "cvrplib": "Augerat A/B/P", "solomon": "Solomon"}.get(args.suite, args.suite)
    for fmt in [f.strip() for f in args.formats.split(",") if f.strip()]:
        paths = [plot_performance_profile(prof, OUT / f"{tag}_profile.{fmt}",
                                          title=f"Performance profile, {label}"),
                 plot_quality_ecdf(qual, OUT / f"{tag}_ecdf.{fmt}",
                                   title=f"Gap to {ref_kind}, every run, {label}")]
        if have_traj:
            paths.append(plot_anytime(curves, OUT / f"{tag}_anytime.{fmt}",
                                      title=f"Anytime behaviour, {label}"))
            paths.append(plot_ttt(ttt, OUT / f"{tag}_ttt.{fmt}",
                                  title=f"Time to within {args.eps:g}% of reference, {label}"))
        for p in paths:
            print(f"saved {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
