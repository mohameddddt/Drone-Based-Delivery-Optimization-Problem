"""Static figures.

All plots read from the results store rather than from hardcoded numbers, and
route plots draw the *actual* flown path -- which, when polygonal no-fly zones
are present, bends around them rather than cutting through.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Union

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from drp.core.energy import route_energy
from drp.core.instance import DRPInstance
from drp.core.solution import Solution

PathLike = Union[str, Path]

plt.rcParams.update({"font.size": 11, "axes.grid": True, "grid.alpha": 0.3})

PALETTE = ["#2E75B6", "#C0504D", "#4E8542", "#8064A2", "#F79646", "#4BACC6"]
METHOD_COLOURS = {
    "greedy": "#808080",
    "bnb": "#4E8542",
    "ga": "#2E75B6",
    "sa": "#C0504D",
    "alns": "#8064A2",
}
METHOD_LABELS = {
    "greedy": "Greedy",
    "bnb": "Branch & Bound",
    "ga": "GA",
    "sa": "SA",
    "alns": "ALNS",
}


def _save(fig, path: PathLike) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(p, dpi=150)
    plt.close(fig)
    return p


def route_polyline(inst: DRPInstance, route: Sequence[int]):
    """The flown path as x and y arrays, detouring around any no-fly zones."""
    nodes = [0] + list(route) + [0]
    xs, ys = [], []
    if inst.nofly_zones:
        from drp.geometry.visibility import shortest_path
        for a, b in zip(nodes[:-1], nodes[1:]):
            seg = shortest_path(inst.coords, inst.nofly_zones, a, b)
            pts = seg if not xs else seg[1:]
            xs.extend(p[0] for p in pts)
            ys.extend(p[1] for p in pts)
    else:
        xs = [inst.coords[p][0] for p in nodes]
        ys = [inst.coords[p][1] for p in nodes]
    return xs, ys


def plot_routes(inst: DRPInstance,
                sol: Solution,
                path: PathLike = "routes.png",
                title: Optional[str] = None) -> Path:
    """Draw a solution: depot, customers, no-fly zones and the flown routes."""
    fig, ax = plt.subplots(figsize=(7.5, 7))
    co = inst.coords

    for poly in inst.nofly_zones:
        patch = plt.Polygon(np.array(poly), closed=True, facecolor="#C0504D",
                            alpha=0.16, edgecolor="#C0504D", linestyle="--",
                            linewidth=1.2, zorder=1)
        ax.add_patch(patch)

    for ri, route in enumerate(sol.used_routes()):
        xs, ys = route_polyline(inst, route)
        ax.plot(xs, ys, "-", color=PALETTE[ri % len(PALETTE)], linewidth=1.8,
                zorder=2, label=f"drone {ri + 1} (E={route_energy(inst, route):.0f})")
        ax.plot([co[c][0] for c in route], [co[c][1] for c in route], "o",
                color=PALETTE[ri % len(PALETTE)], markersize=6, zorder=3)

    ax.plot(co[0][0], co[0][1], "k*", markersize=20, zorder=4, label="depot")
    for c in range(1, inst.N):
        ax.annotate(str(c), (co[c][0], co[c][1]), fontsize=8, zorder=5,
                    textcoords="offset points", xytext=(4, 4))

    ax.set_title(title or inst.name)
    ax.legend(fontsize=8)
    ax.set_aspect("equal", adjustable="datalim")
    fig.tight_layout()
    return _save(fig, path)


def plot_method_comparison(recs: Sequence[Dict[str, Any]],
                           methods: Sequence[str],
                           path: PathLike) -> Path:
    names = [r["instance"] for r in recs]
    x = np.arange(len(names))
    width = 0.8 / max(len(methods), 1)

    fig, ax = plt.subplots(figsize=(12, 5))
    for mi, m in enumerate(methods):
        vals = [r.get(f"{m}_best") or np.nan for r in recs]
        ax.bar(x + (mi - (len(methods) - 1) / 2) * width, vals, width,
               label=METHOD_LABELS.get(m, m), color=METHOD_COLOURS.get(m))
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=45, ha="right")
    ax.set_ylabel("Total energy (best)")
    ax.set_title("Best solution energy by method and instance")
    ax.legend()
    fig.tight_layout()
    return _save(fig, path)


def plot_gap_to_reference(recs: Sequence[Dict[str, Any]],
                          methods: Sequence[str],
                          path: PathLike) -> Path:
    names = [r["instance"] for r in recs]
    x = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(12, 4.5))
    for m in methods:
        vals = [r.get(f"{m}_gap_pct") for r in recs]
        ax.plot(x, vals, "o-", label=METHOD_LABELS.get(m, m),
                color=METHOD_COLOURS.get(m))
    for i, r in enumerate(recs):
        if r.get("ref_is_proven_optimum"):
            ax.axvspan(i - 0.5, i + 0.5, color="#4E8542", alpha=0.10)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=45, ha="right")
    ax.set_ylabel("% above reference")
    ax.set_title("Gap to reference (shaded = proven optimum, elsewhere best-known)")
    ax.legend()
    fig.tight_layout()
    return _save(fig, path)


def plot_bnb_dual_gap(recs: Sequence[Dict[str, Any]], path: PathLike) -> Path:
    """Incumbent vs dual bound per instance -- what §5.1 buys us.

    Before the anytime bound, a timed-out run reported a number with no context.
    Now every instance shows the interval the optimum is known to lie in.
    """
    recs = [r for r in recs if r.get("bnb_best") is not None]
    names = [r["instance"] for r in recs]
    x = np.arange(len(names))
    ub = [r["bnb_best"] for r in recs]
    lb = [r.get("bnb_dual") if r.get("bnb_dual") is not None else 0 for r in recs]

    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.vlines(x, lb, ub, color="#4E8542", linewidth=6, alpha=0.35,
              label="proved interval [LB, incumbent]")
    ax.plot(x, ub, "o", color="#4E8542", label="incumbent (upper bound)")
    ax.plot(x, lb, "v", color="#C0504D", label="dual bound (lower bound)")
    for i, r in enumerate(recs):
        if r.get("bnb_opt"):
            ax.annotate("proved", (i, ub[i]), fontsize=7, ha="center",
                        textcoords="offset points", xytext=(0, 8))
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=45, ha="right")
    ax.set_ylabel("Energy")
    ax.set_title("Branch & Bound: where the optimum is known to lie")
    ax.legend(fontsize=9)
    fig.tight_layout()
    return _save(fig, path)


def plot_convergence(histories: Dict[str, Sequence[float]],
                     path: PathLike,
                     title: str = "Convergence") -> Path:
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for method, hist in histories.items():
        if not hist:
            continue
        ax.plot(np.linspace(0, 1, len(hist)), hist,
                color=METHOD_COLOURS.get(method), label=METHOD_LABELS.get(method, method))
    ax.set_xlabel("normalised search progress")
    ax.set_ylabel("best energy")
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    return _save(fig, path)


def plot_runtime(recs: Sequence[Dict[str, Any]],
                 methods: Sequence[str],
                 path: PathLike) -> Path:
    ns = [r["n"] for r in recs]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for m in methods:
        vals = [max(r.get(f"{m}_time") or 1e-3, 1e-3) for r in recs]
        ax.semilogy(ns, vals, "o-", color=METHOD_COLOURS.get(m),
                    label=METHOD_LABELS.get(m, m))
    solved = [r["n"] for r in recs if r.get("bnb_opt")]
    if solved:
        ax.axvline(max(solved) + 0.5, color="gray", linestyle=":", linewidth=1,
                   label=f"B&B tractability limit ($n={max(solved)}$)")
    ax.set_xlabel("Number of customers $n$")
    ax.set_ylabel("Runtime (s, log scale)")
    ax.set_title("Runtime vs instance size")
    ax.set_xticks(ns)
    ax.legend(fontsize=9)
    fig.tight_layout()
    return _save(fig, path)
