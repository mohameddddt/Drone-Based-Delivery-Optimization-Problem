"""Significance testing over the results store (roadmap §6).

Everything in `drp.eval.metrics` reports bests and means with no indication of
whether a difference is real or seed noise -- "ALNS beats GA by 1.0% on
average" says nothing about whether that 1.0% would survive a different set of
seeds. This module answers that question the standard way for comparing
several stochastic solvers over a shared benchmark suite (Demšar 2006):

- **Wilcoxon signed-rank test**, paired by instance, for every pair of
  methods -- is method A's per-instance performance systematically better
  than method B's, or within noise?
- **Friedman test** across *all* methods at once, plus its **Nemenyi**
  post-hoc critical difference -- which pairwise differences survive
  correction for testing every pair, drawn as a critical-difference diagram.
- **Bootstrap confidence intervals** on each method's average gap, so "1027.7"
  in a table becomes "1027.7, 95% CI [.., ..]".

The metric compared throughout is `{method}_mean_gap_pct` from
`drp.eval.metrics.instance_rows` -- the gap of the *mean over seeds* to the
per-instance reference, not the best-of-seeds figure used for the leaderboard.
Best-of-`n` is optimistic and high-variance; the mean is what a paired test
across instances should compare. Deterministic methods (`greedy`, `bnb`) have
only one "seed", so their mean equals their single run.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import stats as _scipy_stats

from drp.eval.metrics import instance_rows

DEFAULT_METRIC = "mean_gap_pct"


def _metric_matrix(rows: Sequence[Dict], methods: Optional[Sequence[str]] = None,
                   metric: str = DEFAULT_METRIC) -> Tuple[List[str], List[str], np.ndarray]:
    """Instances x methods matrix, restricted to instances where every
    requested method has a value -- the complete-block design Friedman and
    the paired Wilcoxon both need."""
    recs = instance_rows(rows)
    all_methods = sorted({r["method"] for r in rows})
    methods = list(methods) if methods else all_methods

    complete_instances, matrix_rows = [], []
    for r in recs:
        values = [r.get(f"{m}_{metric}") for m in methods]
        if all(v is not None for v in values):
            complete_instances.append(r["instance"])
            matrix_rows.append(values)

    matrix = np.array(matrix_rows, dtype=float) if matrix_rows else np.empty((0, len(methods)))
    return methods, complete_instances, matrix


@dataclass
class WilcoxonResult:
    method_a: str
    method_b: str
    metric: str
    n: int
    statistic: Optional[float]
    p_value: Optional[float]
    better: Optional[str]       # the method with the lower (better) mean, or None
    significant: Optional[bool]  # p_value < alpha, or None if untestable


def wilcoxon_pairwise(rows: Sequence[Dict], methods: Optional[Sequence[str]] = None,
                      metric: str = DEFAULT_METRIC,
                      alpha: float = 0.05) -> List[WilcoxonResult]:
    """Wilcoxon signed-rank test for every pair of methods, paired by instance.

    Pairs are formed independently per comparison -- method A vs B uses every
    instance where *both* have a value, even if some other method is missing
    one, so a single infeasible run on one method costs that method's
    comparisons, not everybody's.
    """
    all_methods = sorted({r["method"] for r in rows})
    methods = list(methods) if methods else all_methods
    recs = instance_rows(rows)
    out: List[WilcoxonResult] = []

    for i, a in enumerate(methods):
        for b in methods[i + 1:]:
            xs, ys = [], []
            for r in recs:
                x, y = r.get(f"{a}_{metric}"), r.get(f"{b}_{metric}")
                if x is not None and y is not None:
                    xs.append(x)
                    ys.append(y)
            n = len(xs)
            if n < 1:
                out.append(WilcoxonResult(a, b, metric, 0, None, None, None, None))
                continue
            diffs = np.array(xs) - np.array(ys)
            if np.all(diffs == 0):
                out.append(WilcoxonResult(a, b, metric, n, 0.0, 1.0, None, False))
                continue
            try:
                stat, p = _scipy_stats.wilcoxon(xs, ys, zero_method="pratt")
            except ValueError:
                out.append(WilcoxonResult(a, b, metric, n, None, None, None, None))
                continue
            mean_diff = float(np.mean(diffs))
            better = a if mean_diff < 0 else (b if mean_diff > 0 else None)
            out.append(WilcoxonResult(a, b, metric, n, float(stat), float(p),
                                      better, bool(p < alpha)))
    return out


@dataclass
class FriedmanResult:
    methods: List[str]
    metric: str
    n_instances: int
    statistic: Optional[float]
    p_value: Optional[float]
    avg_ranks: Dict[str, float]
    critical_difference: Optional[float]  # Nemenyi CD at `alpha`, same units as avg_ranks


def friedman_test(rows: Sequence[Dict], methods: Optional[Sequence[str]] = None,
                  metric: str = DEFAULT_METRIC, alpha: float = 0.05) -> FriedmanResult:
    """Friedman test across all methods at once, with average ranks and the
    Nemenyi critical difference for a critical-difference diagram.

    Needs >= 3 methods and >= 2 instances with a complete row (every method
    has a value) to be well-defined; returns `statistic=None` otherwise, with
    ranks still filled in where computable.
    """
    methods, instances, matrix = _metric_matrix(rows, methods, metric)
    n = len(instances)
    k = len(methods)

    if n == 0 or k == 0:
        return FriedmanResult(methods, metric, n, None, None, {}, None)

    # Rank each instance's row ascending (rank 1 = lowest gap = best), with
    # ties averaged -- the standard treatment for the Friedman test.
    ranks = np.apply_along_axis(_average_rank, 1, matrix)
    avg_ranks = {m: float(ranks[:, j].mean()) for j, m in enumerate(methods)}

    cd = nemenyi_critical_difference(k, n, alpha) if k >= 2 and n >= 2 else None

    if k < 3 or n < 2:
        return FriedmanResult(methods, metric, n, None, None, avg_ranks, cd)

    stat, p = _scipy_stats.friedmanchisquare(*[matrix[:, j] for j in range(k)])
    return FriedmanResult(methods, metric, n, float(stat), float(p), avg_ranks, cd)


def _average_rank(row: np.ndarray) -> np.ndarray:
    """Ranks with ties resolved by averaging (SciPy's `rankdata` default)."""
    return _scipy_stats.rankdata(row)


def nemenyi_critical_difference(k: int, n: int, alpha: float = 0.05) -> float:
    """Demšar (2006) critical difference for the Nemenyi post-hoc test:
    two methods' average ranks (over `n` instances, among `k` methods being
    compared) differ significantly at `alpha` if they differ by more than
    this.

        CD = q_alpha * sqrt(k(k+1) / (6n))

    `q_alpha` is the studentized range statistic's critical value divided by
    sqrt(2); computed from `scipy.stats.studentized_range` rather than a
    hardcoded table, so it is exact for any `k`, not just the textbook's
    tabulated ones. `test_stats.py` checks it against Demšar's published
    values for k = 2..10 at alpha = 0.05.
    """
    if k < 2 or n < 1:
        return math.inf
    q_alpha = _scipy_stats.studentized_range.ppf(1 - alpha, k, np.inf) / math.sqrt(2)
    return float(q_alpha * math.sqrt(k * (k + 1) / (6.0 * n)))


def bootstrap_ci(values: Sequence[float], n_boot: int = 10000, alpha: float = 0.05,
                 seed: int = 0) -> Tuple[float, float, float]:
    """(mean, lower, upper) percentile bootstrap CI of the mean of `values`.

    Resamples `values` with replacement `n_boot` times; the interval is the
    `alpha/2` and `1 - alpha/2` percentiles of the resampled means. With one
    value there is nothing to resample, so the interval collapses to a point.
    """
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return math.nan, math.nan, math.nan
    if arr.size == 1:
        return float(arr[0]), float(arr[0]), float(arr[0])
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, arr.size, size=(n_boot, arr.size))
    boot_means = arr[idx].mean(axis=1)
    lo, hi = np.percentile(boot_means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(arr.mean()), float(lo), float(hi)


@dataclass
class SignificanceReport:
    metric: str
    alpha: float
    n_instances: int
    methods: List[str]
    method_ci: Dict[str, Tuple[float, float, float]] = field(default_factory=dict)
    friedman: Optional[FriedmanResult] = None
    pairwise: List[WilcoxonResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "alpha": self.alpha,
            "n_instances": self.n_instances,
            "methods": self.methods,
            "method_ci": {m: {"mean": ci[0], "lo": ci[1], "hi": ci[2]}
                         for m, ci in self.method_ci.items()},
            "friedman": None if self.friedman is None else {
                "statistic": self.friedman.statistic,
                "p_value": self.friedman.p_value,
                "avg_ranks": self.friedman.avg_ranks,
                "critical_difference": self.friedman.critical_difference,
                "n_instances": self.friedman.n_instances,
            },
            "pairwise": [
                {"a": w.method_a, "b": w.method_b, "n": w.n,
                 "statistic": w.statistic, "p_value": w.p_value,
                 "better": w.better, "significant": w.significant}
                for w in self.pairwise
            ],
        }


def significance_report(rows: Sequence[Dict], methods: Optional[Sequence[str]] = None,
                        metric: str = DEFAULT_METRIC, alpha: float = 0.05,
                        n_boot: int = 10000, seed: int = 0) -> SignificanceReport:
    """The full §6 bundle for a results-store query: bootstrap CIs per method,
    the Friedman test with Nemenyi critical difference, and every pairwise
    Wilcoxon comparison."""
    all_methods = sorted({r["method"] for r in rows})
    methods = list(methods) if methods else all_methods
    recs = instance_rows(rows)

    method_ci: Dict[str, Tuple[float, float, float]] = {}
    for m in methods:
        vals = [r[f"{m}_{metric}"] for r in recs if r.get(f"{m}_{metric}") is not None]
        method_ci[m] = bootstrap_ci(vals, n_boot=n_boot, alpha=alpha, seed=seed)

    friedman = friedman_test(rows, methods, metric, alpha)
    pairwise = wilcoxon_pairwise(rows, methods, metric, alpha)

    return SignificanceReport(metric=metric, alpha=alpha, n_instances=friedman.n_instances,
                              methods=methods, method_ci=method_ci,
                              friedman=friedman, pairwise=pairwise)
