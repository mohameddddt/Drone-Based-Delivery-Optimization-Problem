"""Aggregation over the results store.

The two "gap" quantities here mean entirely different things and once collided on
the same key, which silently replaced Branch & Bound's proved interval with its
distance from the best-known value:

  * ``bnb_dual_gap_pct`` -- (incumbent - dual bound) / incumbent. How much of the
    search space the proof did *not* close. Large on timed-out instances.
  * ``bnb_gap_pct``      -- (best - reference) / reference, the same gap every
    method gets. Zero whenever B&B produced the reference value itself.

Conflating them made a 66% unproved interval read as 0.004%.
"""
from __future__ import annotations

import pytest

from drp.eval.metrics import best_known, instance_rows, method_summary


def make_run(instance="I1", method="ga", energy=100.0, **kw):
    row = {
        "instance": instance, "n": 10, "k": 3, "method": method,
        "seed": 1, "time_budget": 5.0, "energy": energy,
        "dual_bound": None, "optimal": 0, "feasible": 1,
        "nodes": None, "iterations": None, "wall_time": 1.0,
    }
    row.update(kw)
    return row


def test_dual_gap_is_not_overwritten_by_the_reference_gap():
    """The regression this module exists for."""
    rows = [
        make_run(method="bnb", energy=839.5, dual_bound=280.4, optimal=0, nodes=99),
        make_run(method="ga", energy=839.5),
    ]
    rec = instance_rows(rows)[0]

    # B&B produced the best value, so its gap to the reference is zero...
    assert rec["bnb_gap_pct"] == pytest.approx(0.0, abs=1e-6)
    # ...but it proved almost nothing, and that must still be visible.
    assert rec["bnb_dual_gap_pct"] == pytest.approx(66.6, abs=0.1)
    assert rec["bnb_dual"] == pytest.approx(280.4)
    assert rec["bnb_opt"] is False


def test_proven_optimum_has_zero_dual_gap():
    rows = [make_run(method="bnb", energy=452.5, dual_bound=452.5, optimal=1)]
    rec = instance_rows(rows)[0]
    assert rec["bnb_opt"] is True
    assert rec["bnb_dual_gap_pct"] == pytest.approx(0.0)
    assert rec["ref"] == pytest.approx(452.5)
    assert rec["ref_is_proven_optimum"] is True


def test_reference_is_the_proven_optimum_when_one_exists():
    """Even if a heuristic reports something lower through rounding noise, the
    proven optimum is the reference."""
    rows = [
        make_run(method="bnb", energy=600.0, dual_bound=600.0, optimal=1),
        make_run(method="ga", energy=610.0),
        make_run(method="sa", energy=605.0),
    ]
    rec = instance_rows(rows)[0]
    assert rec["ref"] == pytest.approx(600.0)
    assert rec["ref_is_proven_optimum"] is True
    assert rec["ga_gap_pct"] == pytest.approx(100 * 10.0 / 600.0, abs=1e-3)


def test_reference_is_best_known_when_nothing_was_proved():
    rows = [
        make_run(method="bnb", energy=900.0, dual_bound=300.0, optimal=0),
        make_run(method="alns", energy=850.0),
    ]
    rec = instance_rows(rows)[0]
    assert rec["ref"] == pytest.approx(850.0)
    assert rec["ref_is_proven_optimum"] is False


def test_infeasible_runs_are_excluded():
    rows = [
        make_run(method="ga", energy=500.0, feasible=0),
        make_run(method="ga", energy=700.0, feasible=1),
    ]
    rec = instance_rows(rows)[0]
    assert rec["ga_best"] == pytest.approx(700.0), \
        "an infeasible run must not be reported as the best"


def test_best_and_mean_over_seeds():
    rows = [
        make_run(method="sa", energy=100.0, seed=1),
        make_run(method="sa", energy=200.0, seed=2),
        make_run(method="sa", energy=300.0, seed=3),
    ]
    rec = instance_rows(rows)[0]
    assert rec["sa_best"] == pytest.approx(100.0)
    assert rec["sa_mean"] == pytest.approx(200.0)


def test_method_summary_counts_optima_against_proven_instances_only():
    rows = [
        make_run(instance="A", method="bnb", energy=100.0, dual_bound=100.0, optimal=1),
        make_run(instance="A", method="ga", energy=100.0),
        make_run(instance="B", method="bnb", energy=900.0, dual_bound=200.0, optimal=0),
        make_run(instance="B", method="ga", energy=800.0),
    ]
    summary = {s["method"]: s for s in method_summary(rows)}
    assert summary["ga"]["n_proven"] == 1
    assert summary["ga"]["optima_found"] == 1
    assert summary["ga"]["avg_gap_pct_on_proven"] == pytest.approx(0.0)


def test_best_known_leaderboard():
    rows = [
        make_run(instance="A", method="ga", energy=500.0),
        make_run(instance="A", method="sa", energy=450.0),
        make_run(instance="B", method="ga", energy=700.0),
    ]
    assert best_known(rows) == {"A": 450.0, "B": 700.0}
