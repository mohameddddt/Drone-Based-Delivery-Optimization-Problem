"""Static figures.

All plots read from the results store rather than from hardcoded numbers, and
route plots draw the *actual* flown path -- which, when polygonal no-fly zones
are present, bends around them rather than cutting through.

Two things every plot here obeys (roadmap 2.5):

**Format comes from the extension.** `-o routes.svg`, `.pdf` and `.eps` work
exactly as `.png` does, because matplotlib picks the backend off the suffix.
`save_figure` only has to stop forcing a raster dpi on a vector target and give
vector output the linewidths and fonts it deserves; at dpi=150 a hairline is
about 0.4 device pixels and disappears, which is what was hiding the fact that
some of these strokes were too thin for print.

**Colour is never the only channel.** Every series gets a colour *and* a dash
pattern *and* a marker (or a bar hatch) from `drp.viz.theme`, indexed together,
so a figure survives a greyscale print and a dichromatic reader. Pass
``theme="chart"`` to any of these to get the original palette back.
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
from drp.viz.theme import Theme, resolve

PathLike = Union[str, Path]

#: Suffixes matplotlib renders as vector geometry rather than pixels.
VECTOR_SUFFIXES = frozenset({".svg", ".svgz", ".pdf", ".eps", ".ps"})

plt.rcParams.update({"font.size": 11, "axes.grid": True, "grid.alpha": 0.3})

# Kept as module constants because `webdata`, `treedata` and `dashdata` have
# imported them by name since 2.2. They are the *default* theme's values;
# anything that wants a specific theme should go through `drp.viz.theme`.
PALETTE = list(resolve().palette)
METHOD_COLOURS = dict(resolve().method_colors)
METHOD_LABELS = {
    "greedy": "Greedy",
    "bnb": "Branch & Bound",
    "ga": "GA",
    "sa": "SA",
    "alns": "ALNS",
}


def is_vector(path: PathLike) -> bool:
    return Path(path).suffix.lower() in VECTOR_SUFFIXES


def save_figure(fig, path: PathLike, dpi: int = 150) -> Path:
    """Save `fig` to `path`, letting the extension choose the format.

    `dpi` is applied to raster targets only. Passing it to a vector backend
    does not change the geometry -- it only rescales the notional pixel grid
    that a few effects (hatch density, rasterised images) are quantised on --
    and PDF in particular embeds it in a way that makes two otherwise identical
    files differ, so it is left off.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if is_vector(p):
        # `metadata` is stripped for SVG and PDF: matplotlib stamps a creation
        # date by default, which makes every regeneration a diff.
        kw: Dict[str, Any] = {}
        if p.suffix.lower() in (".svg", ".svgz"):
            kw["metadata"] = {"Date": None}
        elif p.suffix.lower() == ".pdf":
            kw["metadata"] = {"CreationDate": None}
        fig.savefig(p, **kw)
    else:
        fig.savefig(p, dpi=dpi)
    plt.close(fig)
    return p


#: Kept under its old private name; `_save` is called all over this module.
_save = save_figure


def save_figure_formats(fig, path: PathLike, formats: Sequence[str],
                        dpi: int = 150) -> list:
    """Save one figure once per suffix in `formats`, e.g. ``("png", "svg")``.

    The figure is closed after the last one, so callers must not reuse it.
    """
    base = Path(path)
    out = []
    for i, fmt in enumerate(formats):
        f = fmt if fmt.startswith(".") else f".{fmt}"
        p = base.with_suffix(f)
        p.parent.mkdir(parents=True, exist_ok=True)
        if is_vector(p):
            kw: Dict[str, Any] = {}
            if p.suffix.lower() in (".svg", ".svgz"):
                kw["metadata"] = {"Date": None}
            elif p.suffix.lower() == ".pdf":
                kw["metadata"] = {"CreationDate": None}
            fig.savefig(p, **kw)
        else:
            fig.savefig(p, dpi=dpi)
        out.append(p)
    plt.close(fig)
    return out


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
                title: Optional[str] = None,
                theme: Optional[Union[str, Theme]] = None) -> Path:
    """Draw a solution: depot, customers, no-fly zones and the flown routes.

    Each drone gets a colour, a dash pattern and a marker shape from the theme,
    all three keyed on the same index, so the routes stay separable in
    greyscale and under any colour-vision deficiency.
    """
    th = resolve(theme)
    fig, ax = plt.subplots(figsize=(7.5, 7))
    co = inst.coords

    for poly in inst.nofly_zones:
        patch = plt.Polygon(np.array(poly), closed=True, facecolor=th.restricted,
                            alpha=0.14, edgecolor=th.restricted, linestyle="--",
                            linewidth=1.2, hatch="//", zorder=1)
        ax.add_patch(patch)

    for ri, route in enumerate(sol.used_routes()):
        xs, ys = route_polyline(inst, route)
        ax.plot(xs, ys, color=th.color(ri), linestyle=th.mpl_dash(ri),
                linewidth=1.8, zorder=2,
                label=f"drone {ri + 1} (E={route_energy(inst, route):.0f})")
        ax.plot([co[c][0] for c in route], [co[c][1] for c in route],
                linestyle="none", marker=th.marker(ri), color=th.color(ri),
                markersize=6, markeredgecolor=th.panel, markeredgewidth=0.6,
                zorder=3)

    ax.plot(co[0][0], co[0][1], "*", color=th.ink, markersize=20, zorder=4,
            label="depot")
    for c in range(1, inst.N):
        ax.annotate(str(c), (co[c][0], co[c][1]), fontsize=8, zorder=5,
                    color=th.ink, textcoords="offset points", xytext=(4, 4))

    ax.set_title(title or inst.name)
    ax.legend(fontsize=8)
    ax.set_aspect("equal", adjustable="datalim")
    fig.tight_layout()
    return save_figure(fig, path)


def plot_method_comparison(recs: Sequence[Dict[str, Any]],
                           methods: Sequence[str],
                           path: PathLike,
                           theme: Optional[Union[str, Theme]] = None) -> Path:
    th = resolve(theme)
    names = [r["instance"] for r in recs]
    x = np.arange(len(names))
    width = 0.8 / max(len(methods), 1)

    fig, ax = plt.subplots(figsize=(12, 5))
    for mi, m in enumerate(methods):
        vals = [r.get(f"{m}_best") or np.nan for r in recs]
        ax.bar(x + (mi - (len(methods) - 1) / 2) * width, vals, width,
               label=METHOD_LABELS.get(m, m), color=th.method_color(m, mi),
               hatch=th.hatch(mi), edgecolor=th.panel, linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=45, ha="right")
    ax.set_ylabel("Total energy (best)")
    ax.set_title("Best solution energy by method and instance")
    ax.legend()
    fig.tight_layout()
    return save_figure(fig, path)


def plot_gap_to_reference(recs: Sequence[Dict[str, Any]],
                          methods: Sequence[str],
                          path: PathLike,
                          theme: Optional[Union[str, Theme]] = None) -> Path:
    th = resolve(theme)
    names = [r["instance"] for r in recs]
    x = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(12, 4.5))
    for mi, m in enumerate(methods):
        vals = [r.get(f"{m}_gap_pct") for r in recs]
        ax.plot(x, vals, marker=th.method_marker(m),
                linestyle=th.method_mpl_dash(m), label=METHOD_LABELS.get(m, m),
                color=th.method_color(m, mi))
    for i, r in enumerate(recs):
        if r.get("ref_is_proven_optimum"):
            ax.axvspan(i - 0.5, i + 0.5, color=th.accent, alpha=0.10,
                       hatch="\\\\", edgecolor=th.accent, linewidth=0)
    ax.axhline(0, color=th.ink, linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=45, ha="right")
    ax.set_ylabel("% above reference")
    ax.set_title("Gap to reference (shaded = proven optimum, elsewhere best-known)")
    ax.legend()
    fig.tight_layout()
    return save_figure(fig, path)


def plot_bnb_dual_gap(recs: Sequence[Dict[str, Any]], path: PathLike,
                      theme: Optional[Union[str, Theme]] = None) -> Path:
    """Incumbent vs dual bound per instance -- what 5.1 buys us.

    Before the anytime bound, a timed-out run reported a number with no context.
    Now every instance shows the interval the optimum is known to lie in.
    """
    th = resolve(theme)
    recs = [r for r in recs if r.get("bnb_best") is not None]
    names = [r["instance"] for r in recs]
    x = np.arange(len(names))
    ub = [r["bnb_best"] for r in recs]
    lb = [r.get("bnb_dual") if r.get("bnb_dual") is not None else 0 for r in recs]

    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.vlines(x, lb, ub, color=th.accent, linewidth=6, alpha=0.35,
              label="proved interval [LB, incumbent]")
    ax.plot(x, ub, "o", color=th.accent, label="incumbent (upper bound)")
    ax.plot(x, lb, "v", color=th.caution, label="dual bound (lower bound)")
    for i, r in enumerate(recs):
        if r.get("bnb_opt"):
            ax.annotate("proved", (i, ub[i]), fontsize=7, ha="center",
                        color=th.ink, textcoords="offset points", xytext=(0, 8))
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=45, ha="right")
    ax.set_ylabel("Energy")
    ax.set_title("Branch & Bound: where the optimum is known to lie")
    ax.legend(fontsize=9)
    fig.tight_layout()
    return save_figure(fig, path)


def plot_convergence(histories: Dict[str, Sequence[float]],
                     path: PathLike,
                     title: str = "Convergence",
                     theme: Optional[Union[str, Theme]] = None) -> Path:
    th = resolve(theme)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for mi, (method, hist) in enumerate(histories.items()):
        if not hist:
            continue
        ax.plot(np.linspace(0, 1, len(hist)), hist,
                color=th.method_color(method, mi),
                linestyle=th.method_mpl_dash(method),
                label=METHOD_LABELS.get(method, method))
    ax.set_xlabel("normalised search progress")
    ax.set_ylabel("best energy")
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    return save_figure(fig, path)


def plot_runtime(recs: Sequence[Dict[str, Any]],
                 methods: Sequence[str],
                 path: PathLike,
                 theme: Optional[Union[str, Theme]] = None) -> Path:
    th = resolve(theme)
    ns = [r["n"] for r in recs]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for mi, m in enumerate(methods):
        vals = [max(r.get(f"{m}_time") or 1e-3, 1e-3) for r in recs]
        ax.semilogy(ns, vals, marker=th.method_marker(m),
                    linestyle=th.method_mpl_dash(m),
                    color=th.method_color(m, mi), label=METHOD_LABELS.get(m, m))
    solved = [r["n"] for r in recs if r.get("bnb_opt")]
    if solved:
        ax.axvline(max(solved) + 0.5, color=th.muted, linestyle=":", linewidth=1,
                   label=f"B&B tractability limit ($n={max(solved)}$)")
    ax.set_xlabel("Number of customers $n$")
    ax.set_ylabel("Runtime (s, log scale)")
    ax.set_title("Runtime vs instance size")
    ax.set_xticks(ns)
    ax.legend(fontsize=9)
    fig.tight_layout()
    return save_figure(fig, path)


def plot_theme_swatches(path: PathLike,
                        themes: Sequence[Union[str, Theme]] = ("chart", "safe"),
                        ) -> Path:
    """The before/after: every theme's route palette under every deficiency.

    This is the figure that decides whether the claim in `drp/viz/theme.py` is
    true, so it draws the *simulated* colours rather than describing them --
    each swatch is the colour a dichromat sees, and the stroke below it carries
    the dash pattern that makes the series identifiable when the colour does
    not.
    """
    from drp.viz.cvd import KINDS, simulate

    ths = [resolve(t) for t in themes]
    fig, axes = plt.subplots(len(ths), len(KINDS),
                             figsize=(3.1 * len(KINDS), 1.9 * len(ths)),
                             squeeze=False)
    for r, th in enumerate(ths):
        for c, kind in enumerate(KINDS):
            ax = axes[r][c]
            ax.set_facecolor(th.paper)
            for i, col in enumerate(th.palette):
                sim = simulate(col, kind)
                ax.add_patch(plt.Rectangle((i, 0.38), 0.9, 0.55, color=sim))
                ax.plot([i, i + 0.9], [0.2, 0.2], color=sim, linewidth=2.6,
                        linestyle=th.mpl_dash(i))
            ax.set_xlim(-0.1, len(th.palette))
            ax.set_ylim(0, 1.05)
            ax.set_xticks([])
            ax.set_yticks([])
            ax.grid(False)
            if r == 0:
                ax.set_title(kind, fontsize=10)
            if c == 0:
                ax.set_ylabel(f"{th.name}\n{th.label}", fontsize=9)
    fig.suptitle("Route palette as each kind of colour vision receives it",
                 fontsize=11)
    fig.tight_layout()
    return save_figure(fig, path)
