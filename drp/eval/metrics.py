"""Aggregation over the results store: per-instance rows and per-method summaries.

The reference value for an instance is the Branch & Bound optimum where it was
*proven*, and otherwise the best value any method found. Gaps against a proven
optimum are real optimality gaps; gaps against a best-known are clearly labelled
as such, because conflating the two is how misleading tables get written.
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Dict, List, Optional, Sequence


def instance_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse raw runs into one record per instance."""
    by_inst: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_inst.setdefault(r["instance"], []).append(r)

    out: List[Dict[str, Any]] = []
    for name, runs in by_inst.items():
        rec: Dict[str, Any] = {
            "instance": name,
            "n": runs[0]["n"],
            "K": runs[0]["k"],
        }
        feasible_energies: List[float] = []

        for method in sorted({r["method"] for r in runs}):
            mruns = [r for r in runs
                     if r["method"] == method and r["feasible"] and r["energy"] is not None]
            if not mruns:
                rec[f"{method}_best"] = None
                continue
            energies = [r["energy"] for r in mruns]
            feasible_energies.extend(energies)
            rec[f"{method}_best"] = round(min(energies), 1)
            rec[f"{method}_mean"] = round(statistics.mean(energies), 1)
            rec[f"{method}_time"] = round(sum(r["wall_time"] for r in mruns), 2)
            if method == "bnb":
                b = mruns[0]
                rec["bnb_opt"] = bool(b["optimal"])
                rec["bnb_nodes"] = b["nodes"]
                rec["bnb_dual"] = (None if b["dual_bound"] is None
                                   else round(b["dual_bound"], 1))
                # Deliberately NOT called bnb_gap_pct: that name is claimed
                # below by the gap-to-reference every method gets, and the two
                # mean entirely different things. This one is the *proved*
                # interval (incumbent vs dual bound); that one is distance from
                # the best value anyone found.
                rec["bnb_dual_gap_pct"] = (
                    0.0 if b["optimal"] else
                    (None if not b["energy"] or b["dual_bound"] is None
                     else round(100.0 * (b["energy"] - b["dual_bound"]) / b["energy"], 2))
                )

        proven = rec.get("bnb_opt", False)
        ref = rec.get("bnb_best") if proven else (min(feasible_energies)
                                                 if feasible_energies else None)
        rec["ref"] = None if ref is None else round(ref, 1)
        rec["ref_is_proven_optimum"] = bool(proven)

        if ref:
            for method in sorted({r["method"] for r in runs}):
                best = rec.get(f"{method}_best")
                rec[f"{method}_gap_pct"] = (
                    None if best is None else round(100.0 * (best - ref) / ref, 3))
                mean = rec.get(f"{method}_mean")
                # Gap of the *mean* over seeds, not the best -- the quantity
                # roadmap §6's significance tests compare, since "best of 5
                # seeds" is an optimistic, high-variance statistic and a poor
                # basis for a paired test across a stochastic method.
                rec[f"{method}_mean_gap_pct"] = (
                    None if mean is None else round(100.0 * (mean - ref) / ref, 3))

        out.append(rec)

    out.sort(key=lambda r: (r["n"], r["instance"]))
    return out


def method_summary(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One record per method, aggregated over the instance set."""
    recs = instance_rows(rows)
    proven = [r for r in recs if r.get("ref_is_proven_optimum")]
    methods = sorted({r["method"] for r in rows})

    out = []
    for m in methods:
        energies = [r[f"{m}_best"] for r in recs if r.get(f"{m}_best") is not None]
        times = [r[f"{m}_time"] for r in recs if r.get(f"{m}_time") is not None]
        gaps = [r[f"{m}_gap_pct"] for r in proven
                if r.get(f"{m}_gap_pct") is not None]
        hits = sum(1 for r in proven
                   if r.get(f"{m}_best") is not None
                   and abs(r[f"{m}_best"] - r["ref"]) < 0.05)
        out.append({
            "method": m,
            "instances_solved": len(energies),
            "avg_energy": round(statistics.mean(energies), 1) if energies else None,
            "avg_time_s": round(statistics.mean(times), 2) if times else 0.0,
            "optima_found": hits,
            "n_proven": len(proven),
            "avg_gap_pct_on_proven": (round(statistics.mean(gaps), 3)
                                      if gaps else None),
        })
    return out


def best_known(rows: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    """Best feasible energy seen per instance -- the repository leaderboard."""
    out: Dict[str, float] = {}
    for r in rows:
        if not r["feasible"] or r["energy"] is None:
            continue
        cur = out.get(r["instance"], math.inf)
        out[r["instance"]] = min(cur, r["energy"])
    return out
