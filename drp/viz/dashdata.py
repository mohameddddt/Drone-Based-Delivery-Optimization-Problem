"""Data payload for the metaheuristic convergence dashboard (roadmap §2.4).

Third view built on the same split as `drp/viz/webdata.py` and
`drp/viz/treedata.py`: Python emits one JSON dict, every axis, tween and colour
decision lives in `drp/viz/web/dashboard_template.html`.

What this view is for
---------------------
The flight replay answers "what does this solution look like"; the tree explorer
answers "why did the exact search stop where it did". This one answers **"how
did each metaheuristic get there, and did it get there for a good reason"** —
which is a different question from "which one won", and the one a single
best-energy number cannot address.

Comparing methods honestly
--------------------------
Two things make a naive comparison misleading, and both are handled here rather
than in the page:

* **Iterations are not comparable across methods.** One GA generation evaluates
  `pop_size` tours; one SA iteration evaluates one. Putting them on a shared
  step axis silently claims a GA generation and an SA iteration cost the same.
  Every sample therefore carries elapsed seconds, and seconds is the default
  axis; the step axis is still offered, labelled per method.
* **A single seed is an anecdote.** These are one run each. The payload carries
  the seed and the budget so the page can say so, and it links the reader to
  `drp/eval/stats.py`, which is where distributions over seeds actually live.

Nothing here re-derives search state. `MetaTrace.to_dict` is the solver's own
record; this module adds the instance, the per-method result summary, and the
shared axis limits the page needs to draw them all on one chart.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

from drp.core.energy import total_energy
from drp.core.instance import DRPInstance
from drp.core.solution import Solution
from drp.instances.io import instance_to_dict, solution_to_dict
from drp.meta.trace import MetaTrace
from drp.viz.theme import resolve

#: Colour per method, held constant across every panel on the page. It now
#: comes from the active theme rather than being fixed here -- purple / red /
#: blue was the old set, and its red and blue collapsed onto each other under
#: protanopia. Kept as a module constant because it is part of this module's
#: public surface; `build_dashboard_data` reads the theme, not this.
METHOD_COLOR = {m: resolve().method_color(m)
                for m in ("ga", "sa", "alns")}
#: What one step means, per method -- the axis label has to say this or the
#: step axis is actively misleading.
STEP_LABEL = {
    "ga": "generation",
    "sa": "iteration",
    "alns": "iteration",
}


def _f(v: Optional[float]) -> Optional[float]:
    if v is None or not math.isfinite(v):
        return None
    return float(v)


class MethodRun:
    """One traced run: the trace, and the result summary that goes beside it."""

    def __init__(self, method: str, trace: MetaTrace,
                 best_energy: float, wall_time: float, seed: int,
                 solution: Optional[Solution] = None,
                 extra: Optional[Dict[str, Any]] = None):
        self.method = method
        self.trace = trace
        self.best_energy = best_energy
        self.wall_time = wall_time
        self.seed = seed
        self.solution = solution
        self.extra = dict(extra or {})


def build_dashboard_data(inst: DRPInstance,
                         runs: Sequence[MethodRun],
                         reference: Optional[float] = None,
                         reference_label: str = "",
                         title: Optional[str] = None,
                         theme=None) -> Dict[str, Any]:
    """Everything the dashboard needs, as one JSON-serialisable dict.

    `reference`, when given, is a known-good energy to draw as a floor across
    every panel -- typically B&B's proven optimum, which turns "it converged"
    into "it converged to the right answer" or, more usefully, does not.

    `theme` is a name or a `drp.viz.theme.Theme`. Each method carries a dash
    pattern beside its colour, so three curves crossing in one chart stay three
    curves without relying on hue.
    """
    th = resolve(theme)
    if not runs:
        raise ValueError("no runs to plot; pass at least one traced run")
    for r in runs:
        if r.trace is None:
            raise ValueError(
                f"{r.method}: no trace; call the solver with trace=True")

    t_max = 0.0
    step_max = 0
    e_lo, e_hi = math.inf, -math.inf
    for r in runs:
        for s in r.trace.samples:
            t_max = max(t_max, s.t)
            step_max = max(step_max, s.step)
            for v in (s.best, s.current, s.mean):
                if v is not None and math.isfinite(v):
                    e_lo = min(e_lo, v)
                    e_hi = max(e_hi, v)
    if reference is not None and math.isfinite(reference):
        e_lo = min(e_lo, reference)
    if not math.isfinite(e_lo):
        e_lo, e_hi = 0.0, 1.0
    if e_hi <= e_lo:
        e_hi = e_lo + 1.0

    methods: List[Dict[str, Any]] = []
    for r in runs:
        methods.append({
            "method": r.method,
            "label": r.method.upper(),
            "color": th.method_color(r.method, len(methods)),
            "dash": th.method_dash(r.method),
            "step_label": STEP_LABEL.get(r.method, "step"),
            "seed": int(r.seed),
            "best_energy": _f(r.best_energy),
            "wall_time": float(r.wall_time),
            "trace": r.trace.to_dict(),
            "solution": (solution_to_dict(inst, r.solution, method=r.method)
                         if r.solution is not None else None),
            "extra": r.extra,
        })

    best = min((m["best_energy"] for m in methods
                if m["best_energy"] is not None), default=None)

    return {
        "instance": instance_to_dict(inst),
        "theme": th.to_dict(),
        "methods": methods,
        "reference": _f(reference),
        "reference_label": reference_label,
        "meta": {
            "title": title or f"{inst.name} -- convergence",
            "t_max": float(t_max),
            "step_max": int(step_max),
            "e_lo": float(e_lo),
            "e_hi": float(e_hi),
            "best_overall": best,
        },
    }


def run_summary(inst: DRPInstance, sol: Optional[Solution]) -> Optional[float]:
    """The energy of `sol`, or None. Used to cross-check a reported best."""
    if sol is None:
        return None
    e = total_energy(inst, sol)
    return None if math.isinf(e) else float(e)
