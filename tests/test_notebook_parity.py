"""Parity with the graded notebook.

`Van Der Linde_Code.ipynb` is a frozen academic artefact: the marks are in, and
its numbers appear in the report. The package was refactored out of it, so these
tests pin the values that must never move.

Only *proven optima* are pinned. Node counts are deliberately not: the package's
Branch & Bound explores children cheapest-bound-first, which visits a different
(generally smaller) tree than the notebook's index-order search. The optimum it
proves is the same -- which is the property that matters.
"""
from __future__ import annotations

import pytest

from drp.core import total_energy
from drp.exact.bnb import solve_bnb
from drp.instances import default_benchmark_suite
from drp.meta.construct import best_construction

# Proven optima from the committed run, reproduced by the notebook and the
# package alike.
PROVEN_OPTIMA = {
    "S1_n5_k2": 452.5,
    "S2_n6_k2": 592.5,
    "S3_n7_k2": 568.5,
    "S4_n8_k3": 670.5,
    "S5_n9_k3": 593.7,
}

GREEDY_ENERGIES = {
    "S1_n5_k2": 567.3,
    "S2_n6_k2": 624.8,
    "S3_n7_k2": 639.3,
    "S4_n8_k3": 691.5,
    "S5_n9_k3": 740.3,
    "S6_n10_k3": 925.1,
    "M1_n12_k4": 1035.7,
}

SUITE = {i.name: i for i in default_benchmark_suite()}


def test_benchmark_suite_shape_is_unchanged():
    suite = default_benchmark_suite()
    assert len(suite) == 12
    assert [i.n_customers for i in suite] == [5, 6, 7, 8, 9, 10, 12, 15, 18, 20, 25, 30]
    assert [i.n_drones for i in suite] == [2, 2, 3, 3, 3, 3, 4, 4, 5, 5, 6, 6]


@pytest.mark.parametrize("name,expected", sorted(GREEDY_ENERGIES.items()))
def test_greedy_construction_is_unchanged(name, expected):
    """The generator and the constructions must still produce the same numbers,
    or the whole committed results table silently shifts."""
    inst = SUITE[name]
    sol = best_construction(inst)
    assert sol is not None
    assert total_energy(inst, sol) == pytest.approx(expected, abs=0.05)


@pytest.mark.slow
@pytest.mark.parametrize("name,expected", sorted(PROVEN_OPTIMA.items()))
def test_proven_optima_are_unchanged(name, expected):
    inst = SUITE[name]
    res = solve_bnb(inst, time_limit=120.0, warm_start=best_construction(inst))

    assert res.optimal, f"{name} should be provable within the time limit"
    assert res.best_energy == pytest.approx(expected, abs=0.05), (
        f"{name}: package proves {res.best_energy:.1f}, the report says {expected}")
    assert res.gap == pytest.approx(0.0, abs=1e-9)


@pytest.mark.slow
@pytest.mark.parametrize("name", sorted(PROVEN_OPTIMA))
def test_metaheuristics_never_beat_a_proven_optimum(name):
    """The single most important invariant in the project.

    A heuristic returning less than a proven optimum would mean the objective,
    the feasibility check, or the exact method is wrong. Everything the report
    concludes rests on this holding.
    """
    from drp.eval.runner import solve_one

    inst = SUITE[name]
    optimum = PROVEN_OPTIMA[name]
    for method in ("ga", "sa", "alns"):
        res = solve_one(inst, method, seed=1, time_limit=3.0)
        assert res.feasible, f"{method} produced an infeasible solution on {name}"
        assert res.energy >= optimum - 0.05, (
            f"{method} returned {res.energy:.2f} on {name}, below the proven "
            f"optimum {optimum} -- something is wrong with the model")
