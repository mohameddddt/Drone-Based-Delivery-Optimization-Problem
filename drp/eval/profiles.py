"""Benchmarking beyond significance tests (roadmap §6, the profiling half).

`drp.eval.stats` answers *whether* two methods differ. This module answers the
questions a p-value cannot:

- **Performance profiles** (Dolan & Moré 2002). For each instance, divide every
  method's energy by the best energy any method reached; a method's profile
  ``rho(tau)`` is the share of instances it solved within a factor ``tau`` of
  the best. ``rho(1)`` is how often it won outright, and how fast the curve
  climbs is how badly it loses when it does not. Unlike an average, one
  disastrous instance cannot dominate it.
- **ECDF of solution quality.** Every run's gap to the reference, as a
  cumulative distribution -- the whole spread over seeds and instances rather
  than a mean and an interval.
- **Anytime curves and the primal integral** (Berthold 2013). Every run records
  ``(seconds, energy)`` whenever its best improved, so the gap can be read at
  any moment of the budget, and the area under the normalised gap is one number
  that rewards being good *early*, which a final-energy table never sees.
- **Time-to-target** (Aiex, Resende & Ribeiro 2007). The first moment a run is
  within ``eps`` of the reference, as an ECDF over runs; runs that never get
  there are right-censored and reported as such, not dropped.
- **Instance-hardness correlation.** Cheap structural features of an instance
  (size, fleet utilisation, battery slack, spatial clustering, how often a
  random tour Splits feasibly) against how far a method finished from the
  reference, by Spearman correlation -- and again controlling for `n`, because
  nearly every difficulty measure grows with size and would otherwise look
  predictive for that reason alone.

Every function takes plain results-store rows, so it runs on any stored study
without re-solving. Only the anytime and time-to-target analyses need the
``extra["anytime"]`` trajectories, which runs record from this branch onwards;
older rows are skipped by those two, and the functions say how many were used.
"""
from __future__ import annotations

import json
import math
import random
import statistics
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from scipy import stats as _scipy_stats

Trajectory = List[Tuple[float, float]]

#: Gaps smaller than this (in percent) are ties with the reference.
GAP_TIE_PCT = 1e-7


# ---------------------------------------------------------------------------
# Shared plumbing
# ---------------------------------------------------------------------------
def _methods(rows: Sequence[Dict], methods: Optional[Sequence[str]]) -> List[str]:
    if methods:
        return list(methods)
    seen: List[str] = []
    for r in rows:
        if r["method"] not in seen:
            seen.append(r["method"])
    return seen


def _energy(r: Dict) -> float:
    if not r.get("feasible") or r.get("energy") is None:
        return math.inf
    return float(r["energy"])


def reference_values(rows: Sequence[Dict],
                     published: Optional[Mapping[str, float]] = None) -> Dict[str, float]:
    """The per-instance reference every gap in this module is measured against.

    The same rule as `drp.eval.metrics.instance_rows`, unrounded: the B&B
    optimum where it was proven, otherwise the best feasible energy any method
    found. A `published` value (a CVRPLIB optimum, say) overrides both -- which
    is what makes a gap a gap to the literature rather than to ourselves.
    """
    refs: Dict[str, float] = {}
    for r in rows:
        e = _energy(r)
        if math.isfinite(e):
            refs[r["instance"]] = min(refs.get(r["instance"], math.inf), e)
    for r in rows:
        if r["method"] == "bnb" and r.get("optimal") and math.isfinite(_energy(r)):
            refs[r["instance"]] = _energy(r)
    for name, v in (published or {}).items():
        if v is not None:
            refs[name] = float(v)
    return refs


def gap_pct(energy: float, ref: float) -> float:
    """Relative gap in percent; ``inf`` for no solution.

    Gaps under ``GAP_TIE_PCT`` are returned as exactly 0: the same solution
    scored by two code paths differs in the 14th digit, and on a log axis that
    noise would otherwise draw as a run fifteen decades better than a 0.1% one.
    """
    if not math.isfinite(energy):
        return math.inf
    if ref == 0:
        return 0.0 if energy == 0 else math.inf
    g = 100.0 * (energy - ref) / abs(ref)
    return 0.0 if abs(g) < GAP_TIE_PCT else g


def ecdf(values: Sequence[float]) -> Tuple[List[float], List[float]]:
    """Empirical CDF as step coordinates: ``ys[i]`` is the share of values
    ``<= xs[i]``. Infinite values count in the denominator and never appear on
    the x-axis, so a curve that stops below 1 is showing unsolved runs."""
    n = len(values)
    if n == 0:
        return [], []
    finite = sorted(v for v in values if math.isfinite(v))
    xs, ys = [], []
    for i, v in enumerate(finite):
        if xs and v == xs[-1]:
            ys[-1] = (i + 1) / n
        else:
            xs.append(float(v))
            ys.append((i + 1) / n)
    return xs, ys


# ---------------------------------------------------------------------------
# Performance profiles
# ---------------------------------------------------------------------------
def performance_ratios(rows: Sequence[Dict],
                       methods: Optional[Sequence[str]] = None,
                       statistic: str = "mean") -> Dict[str, Dict[str, float]]:
    """``{instance: {method: ratio}}``, ratio = method's energy / best method's.

    `statistic` chooses what a stochastic method's energy on an instance *is*:
    ``"mean"`` over its feasible seeds (the default, matching `stats`), or
    ``"best"``. A method with no feasible run on an instance gets ``inf``.
    Instances where no method found anything are left out -- there is nothing
    to be a ratio of.
    """
    if statistic not in ("mean", "best"):
        raise ValueError("statistic must be 'mean' or 'best'")
    methods = _methods(rows, methods)
    per: Dict[str, Dict[str, List[float]]] = {}
    for r in rows:
        if r["method"] in methods:
            per.setdefault(r["instance"], {}).setdefault(r["method"], []).append(_energy(r))

    out: Dict[str, Dict[str, float]] = {}
    for inst, by_m in per.items():
        cost: Dict[str, float] = {}
        for m in methods:
            vals = [v for v in by_m.get(m, []) if math.isfinite(v)]
            if not vals:
                cost[m] = math.inf
            else:
                cost[m] = statistics.mean(vals) if statistic == "mean" else min(vals)
        best = min(cost.values())
        if not math.isfinite(best):
            continue
        ratios = {}
        for m, c in cost.items():
            if not math.isfinite(c):
                ratios[m] = math.inf
            elif best <= 0:
                ratios[m] = 1.0 if c <= best else math.inf
            else:
                ratios[m] = c / best
        out[inst] = ratios
    return out


def performance_profile(rows: Sequence[Dict],
                        methods: Optional[Sequence[str]] = None,
                        statistic: str = "mean",
                        taus: Optional[Sequence[float]] = None) -> Dict[str, Any]:
    """Dolan-Moré profile over solution quality.

    Returns ``taus``, ``rho[method]`` (share of instances within ``tau`` of the
    best, at each tau), ``wins[method]`` (``rho(1)``, ties counting for every
    tied method) and ``n_instances``.
    """
    methods = _methods(rows, methods)
    ratios = performance_ratios(rows, methods, statistic)
    n = len(ratios)
    if taus is None:
        finite = [v for rs in ratios.values() for v in rs.values() if math.isfinite(v)]
        top = max(finite) if finite else 1.0
        top = max(top * 1.02, 1.01)
        taus = sorted(set([1.0] + list(np.linspace(1.0, top, 200))))
    taus = [float(t) for t in taus]
    rho, wins = {}, {}
    for m in methods:
        rs = [ratios[i][m] for i in ratios]
        # A ratio within 1e-9 of the best is a tie, not a loss to float noise.
        rho[m] = [sum(1 for v in rs if v <= t * (1 + 1e-9)) / n if n else 0.0 for t in taus]
        wins[m] = sum(1 for v in rs if v <= 1 + 1e-9) / n if n else 0.0
    return {"statistic": statistic, "n_instances": n, "taus": taus,
            "rho": rho, "wins": wins, "ratios": ratios}


# ---------------------------------------------------------------------------
# Solution quality ECDF
# ---------------------------------------------------------------------------
def quality_ecdf(rows: Sequence[Dict], refs: Mapping[str, float],
                 methods: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Per-run gap-to-reference distribution for each method."""
    methods = _methods(rows, methods)
    out: Dict[str, Any] = {}
    for m in methods:
        gaps = [gap_pct(_energy(r), refs[r["instance"]])
                for r in rows if r["method"] == m and r["instance"] in refs]
        xs, ys = ecdf(gaps)
        finite = [g for g in gaps if math.isfinite(g)]
        out[m] = {"xs": xs, "ys": ys, "runs": len(gaps),
                  "unsolved": len(gaps) - len(finite),
                  "median": statistics.median(gaps) if gaps else None,
                  "p90": float(np.percentile(finite, 90)) if finite else None}
    return out


# ---------------------------------------------------------------------------
# Anytime behaviour
# ---------------------------------------------------------------------------
def trajectory(row: Dict) -> Optional[Trajectory]:
    """The ``(seconds, energy)`` anytime trajectory stored with a run, if any."""
    extra = row.get("extra")
    if isinstance(extra, str):
        try:
            extra = json.loads(extra) if extra else {}
        except ValueError:
            return None
    pts = (extra or {}).get("anytime")
    if not pts:
        return None
    return [(float(t), float(e)) for t, e in pts]


def value_at(traj: Trajectory, t: float) -> float:
    """Best energy the run held at time `t`; ``inf`` before its first point."""
    best = math.inf
    for ti, e in traj:
        if ti > t:
            break
        best = min(best, e)
    return best


def time_to_target(traj: Trajectory, target: float) -> float:
    """First time the run's best was ``<= target``; ``inf`` if never."""
    for t, e in traj:
        if e <= target:
            return t
    return math.inf


def primal_gap(energy: float, ref: float) -> float:
    """Berthold's normalised primal gap, in ``[0, 1]``: 1 with no solution,
    0 at the reference, and ``(e - ref) / max(e, ref)`` in between. Bounded,
    so a run's first seconds without a solution cost a finite, fixed amount."""
    if not math.isfinite(energy):
        return 1.0
    if energy <= ref:
        return 0.0
    denom = max(abs(energy), abs(ref))
    return min(1.0, (energy - ref) / denom) if denom > 0 else 0.0


def primal_integral(traj: Trajectory, ref: float, budget: float) -> float:
    """Integral of the primal gap over ``[0, budget]``, divided by the budget.

    0 means the reference was held from the first instant; 1 means no solution
    for the whole budget. Two runs ending at the same energy differ here by how
    early they got there.
    """
    if budget <= 0:
        return math.nan
    area, t_prev, g_prev = 0.0, 0.0, 1.0
    for t, e in traj:
        t = min(max(t, 0.0), budget)
        area += g_prev * (t - t_prev)
        t_prev, g_prev = t, min(g_prev, primal_gap(e, ref))
    area += g_prev * (budget - t_prev)
    return area / budget


def _traj_rows(rows, refs, methods):
    for r in rows:
        if r["method"] in methods and r["instance"] in refs:
            tr = trajectory(r)
            if tr is not None:
                yield r, tr


def anytime_curves(rows: Sequence[Dict], refs: Mapping[str, float],
                   methods: Optional[Sequence[str]] = None,
                   grid: Optional[Sequence[float]] = None,
                   points: int = 100) -> Dict[str, Any]:
    """Gap-to-reference over time, aggregated over every run of each method.

    For each time in `grid` (default: `points` log-spaced steps up to the
    longest budget), reports the median and mean percentage gap and the share
    of runs holding a solution. The median counts runs without one as ``inf``
    rather than excluding them, so it cannot improve by losing the hard runs.
    Also reports each method's mean primal integral over its own budget.
    """
    methods = _methods(rows, methods)
    runs = list(_traj_rows(rows, refs, methods))
    budgets = [float(r["time_budget"]) for r, _ in runs if r.get("time_budget")]
    horizon = max(budgets) if budgets else 1.0
    if grid is None:
        grid = list(np.geomspace(min(1e-3, horizon / 1000), horizon, points))
    grid = [float(g) for g in grid]

    out: Dict[str, Any] = {"grid": grid, "methods": {}}
    for m in methods:
        mine = [(r, tr) for r, tr in runs if r["method"] == m]
        med, mean, solved = [], [], []
        for t in grid:
            gaps = [gap_pct(value_at(tr, t), refs[r["instance"]]) for r, tr in mine]
            if not gaps:
                med.append(None); mean.append(None); solved.append(0.0)
                continue
            finite = [g for g in gaps if math.isfinite(g)]
            m_val = float(np.median(gaps))
            med.append(m_val if math.isfinite(m_val) else None)
            mean.append(statistics.mean(finite) if finite else None)
            solved.append(len(finite) / len(gaps))
        integrals = [primal_integral(tr, refs[r["instance"]], float(r["time_budget"]))
                     for r, tr in mine if r.get("time_budget")]
        out["methods"][m] = {
            "runs": len(mine), "median_gap": med, "mean_gap": mean,
            "solved_share": solved,
            "primal_integral": statistics.mean(integrals) if integrals else None,
        }
    return out


def ttt_ecdf(rows: Sequence[Dict], refs: Mapping[str, float],
             methods: Optional[Sequence[str]] = None,
             eps_pct: float = 1.0) -> Dict[str, Any]:
    """Time-to-target distribution per method, target = reference x (1 + eps).

    Runs that never reach the target are censored: they count in the
    denominator and appear in `censored`, so ``ys[-1]`` is the success rate.
    """
    methods = _methods(rows, methods)
    out: Dict[str, Any] = {"eps_pct": eps_pct, "methods": {}}
    for m in methods:
        times = []
        for r, tr in _traj_rows(rows, refs, [m]):
            ref = refs[r["instance"]]
            target = ref + abs(ref) * eps_pct / 100.0 + 1e-9
            times.append(time_to_target(tr, target))
        xs, ys = ecdf(times)
        reached = [t for t in times if math.isfinite(t)]
        out["methods"][m] = {"xs": xs, "ys": ys, "runs": len(times),
                             "censored": len(times) - len(reached),
                             "success_rate": (len(reached) / len(times)) if times else None,
                             "median_reached_s": statistics.median(reached) if reached else None}
    return out


# ---------------------------------------------------------------------------
# Instance hardness
# ---------------------------------------------------------------------------
FEATURES = ("n", "K", "customers_per_drone", "utilisation", "battery_slack",
            "clark_evans", "split_feasible_share")


def instance_features(inst, samples: int = 300, seed: int = 0) -> Dict[str, float]:
    """Cheap structural descriptors of an instance.

    - ``utilisation``: total demand over total fleet payload -- the pressure
      that froze every method on the Augerat sets.
    - ``battery_slack``: battery over the energy of the costliest single-customer
      out-and-back trip. ``inf`` for an unbounded battery; near 1 means some
      customer barely fits in a route on its own.
    - ``clark_evans``: mean nearest-neighbour distance among customers over its
      expectation for the same number of points spread uniformly over their
      bounding box. ~1 is uniform, well below 1 is clustered.
    - ``split_feasible_share``: share of `samples` random giant tours that
      Split into a feasible solution -- the tightness probe PROGRESS used to
      diagnose the Pontianak suite, now a reusable measurement.
    """
    from drp.core.energy import route_energy
    from drp.meta.encoding import random_tour
    from drp.meta.split import split

    n, k = int(inst.n_customers), int(inst.n_drones)
    demand = np.asarray(inst.demand, dtype=float)
    util = float(demand[1:].sum() / (k * inst.payload)) if inst.payload > 0 else math.inf

    worst_trip = max((route_energy(inst, [c]) for c in range(1, inst.N)), default=0.0)
    if not math.isfinite(inst.battery):
        slack = math.inf
    elif worst_trip <= 0 or not math.isfinite(worst_trip):
        slack = math.nan
    else:
        slack = float(inst.battery / worst_trip)

    d = np.array(inst.dist[1:, 1:], dtype=float)
    ce = math.nan
    if n >= 2:
        np.fill_diagonal(d, np.inf)
        mean_nn = float(np.mean(d.min(axis=1)))
        coords = np.asarray(inst.coords, dtype=float)[1:]
        span = coords.max(axis=0) - coords.min(axis=0)
        if inst.geodesic:
            from drp.geometry.distance import KM_PER_DEGREE
            lat = math.radians(float(coords[:, 0].mean()))
            area = (span[0] * KM_PER_DEGREE) * (span[1] * KM_PER_DEGREE * math.cos(lat))
        else:
            area = float(span[0] * span[1])
        if area > 0:
            ce = mean_nn / (0.5 * math.sqrt(area / n))

    rng = random.Random(seed)
    ok = 0
    for _ in range(samples):
        _, e = split(inst, random_tour(inst, rng))
        ok += math.isfinite(e)

    return {"n": float(n), "K": float(k), "customers_per_drone": n / k if k else math.inf,
            "utilisation": util, "battery_slack": slack, "clark_evans": float(ce),
            "split_feasible_share": ok / samples if samples else math.nan}


def _partial_spearman(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> Tuple[float, float]:
    """Spearman correlation of x and y with the rank-linear effect of z removed."""
    rx, ry, rz = (_scipy_stats.rankdata(v) for v in (x, y, z))
    if np.ptp(rz) == 0:
        res = _scipy_stats.pearsonr(rx, ry)
        return float(res[0]), float(res[1])
    def resid(a):
        slope, intercept = np.polyfit(rz, a, 1)
        return a - (slope * rz + intercept)
    ex, ey = resid(rx), resid(ry)
    if np.ptp(ex) == 0 or np.ptp(ey) == 0:
        return math.nan, math.nan
    r, _ = _scipy_stats.pearsonr(ex, ey)
    # One degree of freedom spent on z.
    dof = len(x) - 3
    if dof <= 0 or abs(r) >= 1:
        return float(r), math.nan
    t = r * math.sqrt(dof / (1 - r * r))
    return float(r), float(2 * _scipy_stats.t.sf(abs(t), dof))


def hardness_correlation(features: Mapping[str, Mapping[str, float]],
                         outcome: Mapping[str, float],
                         control: str = "n") -> List[Dict[str, Any]]:
    """Spearman correlation of each feature with `outcome` across instances,
    raw and controlling for `control`. Instances where either value is not
    finite are left out of that feature's test, and `n` says how many remain."""
    names = [f for f in FEATURES if any(f in fs for fs in features.values())]
    out = []
    for f in names:
        xs, ys, zs = [], [], []
        for inst, fs in features.items():
            x, y, z = fs.get(f), outcome.get(inst), fs.get(control)
            if x is None or y is None or z is None:
                continue
            if not all(math.isfinite(v) for v in (x, y, z)):
                continue
            xs.append(x); ys.append(y); zs.append(z)
        row: Dict[str, Any] = {"feature": f, "n": len(xs), "rho": None, "p": None,
                               "partial_rho": None, "partial_p": None}
        if len(xs) >= 4 and np.ptp(xs) > 0 and np.ptp(ys) > 0:
            res = _scipy_stats.spearmanr(xs, ys)
            row["rho"], row["p"] = float(res[0]), float(res[1])
            # A constant control (one Solomon size) removes nothing; reporting
            # the raw value again as "controlled" would overstate the check.
            if f != control and np.ptp(zs) > 0:
                pr, pp = _partial_spearman(np.array(xs), np.array(ys), np.array(zs))
                row["partial_rho"] = None if math.isnan(pr) else pr
                row["partial_p"] = None if math.isnan(pp) else pp
        out.append(row)
    return out


def mean_gap_by_instance(rows: Sequence[Dict], refs: Mapping[str, float],
                         method: str) -> Dict[str, float]:
    """A method's mean gap over its seeds, per instance (``inf`` if any seed
    found nothing -- an unsolved run is not a small gap)."""
    per: Dict[str, List[float]] = {}
    for r in rows:
        if r["method"] == method and r["instance"] in refs:
            per.setdefault(r["instance"], []).append(gap_pct(_energy(r), refs[r["instance"]]))
    return {i: (statistics.mean(g) if all(math.isfinite(v) for v in g) else math.inf)
            for i, g in per.items()}
