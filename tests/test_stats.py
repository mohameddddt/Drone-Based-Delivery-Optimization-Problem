"""Significance testing (roadmap §6).

Three things worth checking hardest:

1. The Nemenyi critical difference matches Demšar (2006)'s published table --
   it isn't hand-typed here, it's derived from the studentized range
   distribution, and a derivation bug would be invisible without a reference.
2. A method that is genuinely, consistently better wins the pairwise Wilcoxon
   test and gets the lower (better) Friedman rank; a method with no real
   difference from another does not manufacture significance out of noise.
3. `bootstrap_ci` brackets the true mean at the stated confidence on data
   with known distributional properties, and degenerates sensibly for a
   single observation.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from drp.eval.stats import (bootstrap_ci, friedman_test,
                            nemenyi_critical_difference, significance_report,
                            wilcoxon_pairwise)

# Demsar (2006), Table 5: q_alpha for the Nemenyi test at alpha = 0.05.
DEMSAR_Q_005 = {2: 1.960, 3: 2.343, 4: 2.569, 5: 2.728, 6: 2.850,
               7: 2.949, 8: 3.031, 9: 3.102, 10: 3.164}


@pytest.mark.parametrize("k", list(DEMSAR_Q_005))
def test_nemenyi_cd_matches_demsar_table(k):
    n = 10
    cd = nemenyi_critical_difference(k, n, alpha=0.05)
    expected = DEMSAR_Q_005[k] * math.sqrt(k * (k + 1) / (6.0 * n))
    assert cd == pytest.approx(expected, rel=1e-3)


def test_nemenyi_cd_shrinks_with_more_instances():
    """More evidence should tighten the critical difference."""
    cd_small = nemenyi_critical_difference(5, 5, alpha=0.05)
    cd_large = nemenyi_critical_difference(5, 50, alpha=0.05)
    assert cd_large < cd_small


def make_run(instance, method, energy, seed=1, **kw):
    row = {
        "instance": instance, "n": 10, "k": 3, "method": method,
        "seed": seed, "time_budget": 5.0, "energy": energy,
        "dual_bound": None, "optimal": 0, "feasible": 1,
        "nodes": None, "iterations": None, "wall_time": 1.0,
    }
    row.update(kw)
    return row


def _consistently_better_dataset(n_instances=15, seed=0):
    """Method 'good' beats method 'bad' by a small, consistent margin on every
    instance, both jittered by independent per-instance noise -- the
    textbook case a paired test should catch even though neither method's
    raw energies are otherwise comparable across instances."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_instances):
        base = rng.uniform(500, 2000)
        rows.append(make_run(f"I{i}", "bad", base + 20.0 + rng.normal(0, 2)))
        rows.append(make_run(f"I{i}", "good", base + rng.normal(0, 2)))
        rows.append(make_run(f"I{i}", "bnb", base, optimal=1, dual_bound=base))
    return rows


def test_wilcoxon_detects_a_consistent_difference():
    rows = _consistently_better_dataset()
    results = {(r.method_a, r.method_b): r
              for r in wilcoxon_pairwise(rows, methods=["good", "bad"])}
    r = results[("good", "bad")]
    assert r.better == "good"
    assert r.significant is True
    assert r.p_value < 0.01


def test_wilcoxon_identical_methods_is_not_significant():
    """Comparing a method against itself (same energies) must not report a
    winner or manufacture significance from an all-zero difference."""
    rows = _consistently_better_dataset()
    same_as_good = [make_run(r["instance"], "good2", r["energy"])
                    for r in rows if r["method"] == "good"]
    r = wilcoxon_pairwise(rows + same_as_good, methods=["good", "good2"])[0]
    assert r.better is None
    assert r.significant is False


def test_friedman_ranks_the_better_method_lower():
    rows = _consistently_better_dataset()
    res = friedman_test(rows, methods=["good", "bad", "bnb"])
    assert res.avg_ranks["bnb"] < res.avg_ranks["good"] < res.avg_ranks["bad"]
    assert res.p_value is not None and res.p_value < 0.01
    assert res.critical_difference is not None and res.critical_difference > 0


def test_friedman_needs_at_least_three_methods():
    rows = _consistently_better_dataset()
    res = friedman_test(rows, methods=["good", "bad"])
    assert res.statistic is None
    assert res.p_value is None
    # Ranks and the pairwise CD are still meaningful with only two methods.
    assert set(res.avg_ranks) == {"good", "bad"}


def test_bootstrap_ci_brackets_a_known_mean():
    rng = np.random.default_rng(1)
    values = rng.normal(loc=10.0, scale=1.0, size=200)
    mean, lo, hi = bootstrap_ci(list(values), n_boot=2000, alpha=0.05, seed=2)
    assert lo < 10.0 < hi
    assert lo < mean < hi


def test_bootstrap_ci_of_a_single_value_collapses_to_a_point():
    mean, lo, hi = bootstrap_ci([42.0])
    assert (mean, lo, hi) == (42.0, 42.0, 42.0)


def test_bootstrap_ci_of_no_values_is_nan():
    mean, lo, hi = bootstrap_ci([])
    assert math.isnan(mean) and math.isnan(lo) and math.isnan(hi)


def test_significance_report_end_to_end():
    rows = _consistently_better_dataset(n_instances=10)
    report = significance_report(rows, methods=["good", "bad", "bnb"], n_boot=1000)
    assert report.n_instances == 10
    assert set(report.method_ci) == {"good", "bad", "bnb"}
    assert report.friedman is not None and report.friedman.p_value < 0.05
    d = report.to_dict()
    assert d["friedman"]["p_value"] < 0.05
    assert len(d["pairwise"]) == 3  # C(3, 2)


def test_wilcoxon_pairs_only_on_instances_both_methods_have():
    """A method missing a value on some instance (e.g. infeasible run) must
    not silently drop that instance for methods that do have it."""
    rows = [
        make_run("A", "x", 100.0), make_run("A", "y", 110.0),
        make_run("B", "x", 100.0),  # y has nothing on B
        make_run("B", "bnb", 100.0, optimal=1, dual_bound=100.0),
        make_run("A", "bnb", 100.0, optimal=1, dual_bound=100.0),
    ]
    r = wilcoxon_pairwise(rows, methods=["x", "y"])[0]
    assert r.n == 1  # only instance A has both x and y
