"""Animated flight playback (roadmap §2.2).

A static route plot hides the fact that the drones fly *simultaneously*. This
animates a shared clock: every drone moves at the same speed along its own path,
so you see the fleet spread out, the long routes still flying after the short
ones have landed, and each battery draining in real time.

Two things this makes visible that the static figure cannot:

  * **Makespan versus energy.** The objective minimises total energy, not time.
    Watching one drone still out while the others are parked is the clearest
    possible argument for the multi-objective work in §4.8.
  * **Proximity.** When two drones pass within the separation distance the
    marker flashes. Nothing enforces separation yet -- that is §4.5 -- so these
    flashes are exactly the conflicts a deconfliction model would have to
    resolve.

Rendered with matplotlib's animation writers. GIF output uses Pillow, which is
already a matplotlib dependency, so this needs nothing extra.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

import matplotlib
matplotlib.use("Agg")
import matplotlib.animation as animation
import matplotlib.pyplot as plt
import numpy as np

from drp.core.energy import route_energy, route_weight
from drp.core.instance import DRPInstance
from drp.core.solution import Solution
from drp.viz.static import PALETTE, route_polyline

PathLike = Union[str, Path]


def _cumulative(xs: Sequence[float], ys: Sequence[float]) -> np.ndarray:
    pts = np.column_stack([xs, ys])
    seg = np.sqrt(((pts[1:] - pts[:-1]) ** 2).sum(axis=1))
    return np.concatenate([[0.0], np.cumsum(seg)])


class _Flight:
    """One drone's path, resampled so position can be queried by distance flown."""

    def __init__(self, inst: DRPInstance, route: Sequence[int], colour: str):
        self.route = list(route)
        self.colour = colour
        xs, ys = route_polyline(inst, route)
        self.pts = np.column_stack([xs, ys])
        self.cum = _cumulative(xs, ys)
        self.length = float(self.cum[-1]) if len(self.cum) else 0.0
        self.energy = route_energy(inst, route)
        self.payload = route_weight(inst, route)

    def position(self, travelled: float) -> Tuple[float, float]:
        if self.length <= 0:
            return tuple(self.pts[0])
        t = min(travelled, self.length)
        i = int(np.searchsorted(self.cum, t, side="right")) - 1
        i = max(0, min(i, len(self.pts) - 2))
        span = self.cum[i + 1] - self.cum[i]
        frac = 0.0 if span <= 0 else (t - self.cum[i]) / span
        p = self.pts[i] + frac * (self.pts[i + 1] - self.pts[i])
        return float(p[0]), float(p[1])

    def trail(self, travelled: float) -> np.ndarray:
        if self.length <= 0:
            return self.pts[:1]
        t = min(travelled, self.length)
        i = int(np.searchsorted(self.cum, t, side="right"))
        head = np.array([self.position(t)])
        return np.vstack([self.pts[:i], head])

    def progress(self, travelled: float) -> float:
        return 1.0 if self.length <= 0 else min(travelled / self.length, 1.0)


def animate_routes(inst: DRPInstance,
                   sol: Solution,
                   path: PathLike = "playback.gif",
                   frames: int = 160,
                   fps: int = 20,
                   separation: Optional[float] = None,
                   title: Optional[str] = None) -> Path:
    """Render an animated playback of `sol` to a GIF (or MP4, by extension).

    `separation` is the distance below which two drones are flagged as being in
    conflict. Defaults to 3% of the field size.
    """
    flights = [_Flight(inst, r, PALETTE[i % len(PALETTE)])
               for i, r in enumerate(sol.used_routes())]
    if not flights:
        raise ValueError("solution has no non-empty routes to animate")

    co = inst.coords
    span = max(np.ptp(co[:, 0]), np.ptp(co[:, 1])) or 1.0
    if separation is None:
        separation = 0.03 * span
    longest = max(f.length for f in flights) or 1.0

    fig, (ax, bar_ax) = plt.subplots(
        1, 2, figsize=(13, 7), gridspec_kw={"width_ratios": [2.4, 1]})

    # --- static background -------------------------------------------------
    for poly in inst.nofly_zones:
        ax.add_patch(plt.Polygon(np.array(poly), closed=True, facecolor="#C0504D",
                                 alpha=0.16, edgecolor="#C0504D", linestyle="--",
                                 linewidth=1.2, zorder=1))
    for f in flights:
        ax.plot(f.pts[:, 0], f.pts[:, 1], "-", color=f.colour, alpha=0.18,
                linewidth=1.0, zorder=1)
    ax.plot(co[1:, 0], co[1:, 1], "o", color="#444444", markersize=5, zorder=2)
    ax.plot(co[0][0], co[0][1], "k*", markersize=20, zorder=5)
    for c in range(1, inst.N):
        ax.annotate(str(c), (co[c][0], co[c][1]), fontsize=7, zorder=5,
                    textcoords="offset points", xytext=(4, 4))

    pad = 0.06 * span
    ax.set_xlim(co[:, 0].min() - pad, co[:, 0].max() + pad)
    ax.set_ylim(co[:, 1].min() - pad, co[:, 1].max() + pad)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(title or f"{inst.name} -- fleet playback")
    ax.grid(alpha=0.25)

    trails = [ax.plot([], [], "-", color=f.colour, linewidth=2.2, zorder=3)[0]
              for f in flights]
    markers = [ax.plot([], [], "o", color=f.colour, markersize=11,
                       markeredgecolor="white", markeredgewidth=1.5, zorder=6)[0]
               for f in flights]
    conflict = ax.plot([], [], "o", color="red", markersize=22, alpha=0.0,
                       zorder=4)[0]
    clock = ax.text(0.02, 0.98, "", transform=ax.transAxes, va="top",
                    fontsize=10, family="monospace")

    # --- battery panel -----------------------------------------------------
    bar_ax.set_xlim(0, 1)
    bar_ax.set_ylim(-0.5, len(flights) - 0.5)
    bar_ax.invert_yaxis()
    bar_ax.set_xlabel("battery remaining")
    bar_ax.set_title("Per-drone battery")
    bar_ax.set_yticks(range(len(flights)))
    bar_ax.set_yticklabels([f"drone {i + 1}" for i in range(len(flights))])
    bar_ax.grid(axis="x", alpha=0.3)

    bars = bar_ax.barh(range(len(flights)), [1.0] * len(flights),
                       color=[f.colour for f in flights], alpha=0.85)
    labels = [bar_ax.text(0.02, i, "", va="center", fontsize=8) for i in
              range(len(flights))]

    battery = inst.battery if math.isfinite(inst.battery) else max(
        f.energy for f in flights)

    def update(frame: int):
        t = (frame / max(frames - 1, 1)) * longest
        positions: List[Tuple[float, float]] = []

        for i, f in enumerate(flights):
            trail = f.trail(t)
            trails[i].set_data(trail[:, 0], trail[:, 1])
            x, y = f.position(t)
            landed = t >= f.length - 1e-9
            markers[i].set_data([x], [y])
            markers[i].set_alpha(0.35 if landed else 1.0)
            positions.append((x, y))

            frac = f.progress(t)
            used = frac * f.energy
            remaining = max(0.0, 1.0 - used / battery) if battery > 0 else 0.0
            bars[i].set_width(remaining)
            bars[i].set_alpha(0.35 if landed else 0.9)
            labels[i].set_text(
                f"{used:.0f} / {battery:.0f} used"
                + ("  (landed)" if landed else ""))

        # proximity flash -- the conflicts §4.5 would have to resolve
        clash = []
        for i in range(len(positions)):
            for j in range(i + 1, len(positions)):
                if (flights[i].progress(t) < 1.0 and flights[j].progress(t) < 1.0
                        and math.dist(positions[i], positions[j]) < separation):
                    clash.append(((positions[i][0] + positions[j][0]) / 2,
                                  (positions[i][1] + positions[j][1]) / 2))
        if clash:
            conflict.set_data([p[0] for p in clash], [p[1] for p in clash])
            conflict.set_alpha(0.55)
        else:
            conflict.set_data([], [])
            conflict.set_alpha(0.0)

        flying = sum(1 for f in flights if f.progress(t) < 1.0)
        clock.set_text(f"distance flown {t:7.1f}\n"
                       f"airborne      {flying}/{len(flights)}"
                       + ("\nCONFLICT" if clash else ""))
        return trails + markers + [conflict, clock] + list(bars) + labels

    anim = animation.FuncAnimation(fig, update, frames=frames,
                                   interval=1000 / fps, blit=False)

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    writer = "pillow" if out.suffix.lower() == ".gif" else "ffmpeg"
    anim.save(str(out), writer=writer, fps=fps, dpi=110)
    plt.close(fig)
    return out
