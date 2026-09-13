r"""Ablation study (roadmap §6): does each component earn its place?

Every metaheuristic here is a bundle of choices nobody has measured one at a
time -- four destroy and three repair operators, adaptive weights, noise in the
repair, a constructed warm start, SA's reheats. This takes each away in turn,
runs the result on the same instances with the same seeds and budget as the
full method, and tests the difference with a paired Wilcoxon test over
instances.

A component whose removal changes nothing significant is either not pulling
its weight or pulling weight another component can carry; one whose removal
hurts is doing work. Neither verdict is available from a table of the full
method's results, however long.

Usage
-----
    python run_ablation.py                     # 11 hard instances, 3 seeds, 5 s
    python run_ablation.py --quick             # 3 instances, 1 seed, 1 s
    python run_ablation.py --tables-only       # re-analyse the latest group

Instances default to those where the full methods still disagree -- the
synthetic suite from n = 12 and the Pontianak suite from n = 15 -- because an
ablation on an instance every variant solves to optimality measures nothing.

Outputs
-------
    results/ablation_runs.db         every run; variants are stored as
                                     methods named ``alns:-shaw`` and so on
    results/analysis/ablation.json   the comparison table below
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from drp.eval.profiles import (mean_gap_by_instance, primal_integral, reference_values,
                               trajectory)
from drp.eval.runner import solve_one
from drp.eval.stats import wilcoxon_pairwise
from drp.eval.store import ResultStore, RunRecord, git_sha

ROOT = Path(__file__).resolve().parent

#: (variant name, base method, solve_one options, warm start?)
VARIANTS: List[Tuple[str, str, Dict[str, Any], bool]] = [
    ("alns", "alns", {}, True),
    ("alns:-random", "alns", {"destroy_ops": ["worst", "shaw", "route"]}, True),
    ("alns:-worst", "alns", {"destroy_ops": ["random", "shaw", "route"]}, True),
    ("alns:-shaw", "alns", {"destroy_ops": ["random", "worst", "route"]}, True),
    ("alns:-route", "alns", {"destroy_ops": ["random", "worst", "shaw"]}, True),
    ("alns:-greedy", "alns", {"repair_ops": ["regret2", "regret3"]}, True),
    ("alns:-regret2", "alns", {"repair_ops": ["greedy", "regret3"]}, True),
    ("alns:-regret3", "alns", {"repair_ops": ["greedy", "regret2"]}, True),
    ("alns:-adaptive", "alns", {"reaction": 0.0}, True),
    ("alns:-noise", "alns", {"noise": 0.0}, True),
    ("alns:-warm", "alns", {"construct_start": False}, False),
    ("sa", "sa", {}, True),
    ("sa:-reheat", "sa", {"reheat_after": 10 ** 9}, True),
    ("sa:-warm", "sa", {}, False),
    ("ga", "ga", {}, True),
    ("ga:-warm", "ga", {}, False),
]
DESCRIPTIONS = {
    "-random": "no random removal", "-worst": "no worst removal",
    "-shaw": "no Shaw (relatedness) removal", "-route": "no route removal",
    "-greedy": "no greedy insertion", "-regret2": "no regret-2 insertion",
    "-regret3": "no regret-3 insertion",
    "-adaptive": "uniform operator choice (reaction = 0)",
    "-noise": "deterministic repair (noise = 0)",
    "-warm": "random start instead of the constructed one",
    "-reheat": "never reheat",
}


def ablation_instances(limit: int = 0) -> List[Any]:
    from drp.instances import default_benchmark_suite, geo_benchmark_suite
    insts = ([i for i in default_benchmark_suite() if i.n_customers >= 12]
             + [i for i in geo_benchmark_suite() if i.n_customers >= 15])
    return insts[:limit] if limit else insts


def run(instances: Sequence[Any], seeds: Sequence[int], budget: float,
        store: ResultStore, group: str) -> None:
    total = len(instances) * len(seeds) * len(VARIANTS)
    done, t0 = 0, time.time()
    for inst in instances:
        for name, method, options, warm in VARIANTS:
            for seed in seeds:
                r = solve_one(inst, method, seed=seed, time_limit=budget,
                              warm=warm, options=options)
                store.add(RunRecord(
                    instance=inst.name, method=name, n=inst.n_customers,
                    k=inst.n_drones, seed=seed, time_budget=budget,
                    energy=None if math.isinf(r.energy) else r.energy,
                    feasible=r.feasible, iterations=r.iterations,
                    wall_time=r.wall_time, run_group=group,
                    extra={"anytime": r.extra.get("anytime"), "options": options,
                           "warm": warm}))
                done += 1
            print(f"{inst.name:14s} {name:15s} done  "
                  f"[{done}/{total}, {time.time() - t0:.0f}s]")


def analyse(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One record per variant, compared with its own full method."""
    refs = reference_values(rows)
    names = [v[0] for v in VARIANTS if any(r["method"] == v[0] for r in rows)]
    out = []
    for name in names:
        base = name.split(":")[0]
        gaps = mean_gap_by_instance(rows, refs, name)
        finite = [g for g in gaps.values() if math.isfinite(g)]
        pis = [primal_integral(tr, refs[r["instance"]], float(r["time_budget"]))
               for r in rows if r["method"] == name
               for tr in [trajectory(r)] if tr is not None]
        rec: Dict[str, Any] = {
            "variant": name, "base": base,
            "description": DESCRIPTIONS.get(name.partition(":")[2], "full method"),
            "instances": len(gaps),
            "unsolved_instances": len(gaps) - len(finite),
            "mean_gap_pct": statistics.mean(finite) if finite else None,
            "primal_integral": statistics.mean(pis) if pis else None,
        }
        if name != base:
            full = mean_gap_by_instance(rows, refs, base)
            common = [i for i in gaps if i in full
                      and math.isfinite(gaps[i]) and math.isfinite(full[i])]
            rec["delta_gap_pct"] = (statistics.mean(gaps[i] - full[i] for i in common)
                                    if common else None)
            rec["worse_on"] = sum(gaps[i] > full[i] + 1e-9 for i in common)
            rec["better_on"] = sum(gaps[i] < full[i] - 1e-9 for i in common)
            w = wilcoxon_pairwise(rows, methods=[base, name])[0]
            rec["wilcoxon_n"], rec["p_value"] = w.n, w.p_value
            rec["significant"] = w.significant
        out.append(rec)
    return out


def report(table: List[Dict[str, Any]]) -> None:
    print("\n" + "-" * 104)
    print(f"{'variant':15s} {'mean gap':>9s} {'vs full':>8s} {'worse/better':>13s} "
          f"{'p':>8s} {'primal int.':>11s} {'unsolved':>9s}  what was removed")
    print("-" * 104)
    for r in table:
        d = r.get("delta_gap_pct")
        p = r.get("p_value")
        tag = "" if r["variant"] == r["base"] else ("  *" if r.get("significant") else "")
        wb = ("" if r["variant"] == r["base"] else f"{r['worse_on']}/{r['better_on']}")
        mg = r["mean_gap_pct"]
        pi = r["primal_integral"]
        print(f"{r['variant']:15s} {'--' if mg is None else f'{mg:8.2f}%':>9s} "
              f"{'' if d is None else f'{d:+7.2f}':>8s} {wb:>13s} "
              f"{'' if p is None else f'{p:8.3g}':>8s} "
              f"{'--' if pi is None else f'{pi:11.4f}':>11s} "
              f"{r['unsolved_instances']:>4d}/{r['instances']:<4d}  {r['description']}{tag}")
    print("  * paired Wilcoxon over instances, p < 0.05, uncorrected for the "
          f"{sum(1 for r in table if r['variant'] != r['base'])} comparisons")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--meta-time", type=float, default=5.0)
    ap.add_argument("--limit", type=int, default=0, help="first N instances only")
    ap.add_argument("--store", default="results/ablation_runs.db")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--tables-only", action="store_true")
    ap.add_argument("--group")
    args = ap.parse_args()

    store = ResultStore(args.store)
    if args.tables_only:
        group = args.group or store.latest_group()
        if group is None:
            raise SystemExit(f"{args.store} is empty -- run the ablation first.")
    else:
        if args.quick:
            args.seeds, args.meta_time, args.limit = 1, 1.0, args.limit or 3
        from run_experiments import machine_speed
        insts = ablation_instances(args.limit)
        group = time.strftime("run_%Y%m%d_%H%M%S")
        est = len(insts) * args.seeds * len(VARIANTS) * args.meta_time
        print(f"{len(insts)} instances x {len(VARIANTS)} variants x {args.seeds} seeds, "
              f"{args.meta_time}s each (~{est / 60:.0f} min) | code {git_sha()}")
        print(f"machine: {machine_speed():.0f} Split evaluations/s")
        run(insts, list(range(1, args.seeds + 1)), args.meta_time, store, group)

    rows = store.rows(group)
    store.close()
    table = analyse(rows)
    report(table)
    out = ROOT / "results" / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    (out / "ablation.json").write_text(
        json.dumps({"store": args.store, "group": group, "variants": table}, indent=1),
        encoding="utf-8")
    print(f"\nwrote results/analysis/ablation.json (group {group}, {len(rows)} runs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
