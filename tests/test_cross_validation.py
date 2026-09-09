"""Cross-validation between the two formulations, and between the solvers.

The notebook printed the F2-vs-B&B comparison and left the reader to eyeball it.
Here it is an assertion.

Formulation 2 omits the per-route battery limit -- that is a path constraint the
commodity-flow model cannot express -- so its optimum is a valid *lower bound*:
equal to the B&B optimum when the battery does not bind, strictly below it when
it does. Anything else means one of the two models is wrong.
"""
from __future__ import annotations

import math

import pytest

from drp.exact.bnb import solve_bnb
from drp.exact.milp_flow import solve_formulation2
from drp.instances import default_benchmark_suite, generate_instance
from drp.meta.construct import best_construction

pulp = pytest.importorskip("pulp", reason="Formulation 2 needs PuLP + CBC")

SMALL = [i for i in default_benchmark_suite() if i.n_customers <= 8]


@pytest.mark.slow
@pytest.mark.parametrize("inst", SMALL, ids=lambda i: i.name)
def test_formulation2_is_a_valid_lower_bound(inst):
    obj, status = solve_formulation2(inst, time_limit=120.0)
    if obj is None:
        pytest.skip(f"F2 unavailable: {status}")

    res = solve_bnb(inst, time_limit=120.0, warm_start=best_construction(inst))
    assert res.optimal, "B&B did not prove optimality on a small instance"

    assert obj <= res.best_energy + 1e-3, (
        f"Formulation 2 returned {obj:.3f}, above the proven optimum "
        f"{res.best_energy:.3f} -- it must be a lower bound")


@pytest.mark.slow
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_formulation2_matches_bnb_when_battery_is_slack(seed):
    """With the battery effectively removed, the two models describe the same
    problem and must agree exactly."""
    inst = generate_instance(f"cv{seed}", 6, 3, 500 + seed)
    inst.battery = math.inf

    obj, status = solve_formulation2(inst, time_limit=120.0)
    if obj is None:
        pytest.skip(f"F2 unavailable: {status}")

    res = solve_bnb(inst, time_limit=120.0, warm_start=best_construction(inst))
    assert res.optimal
    assert obj == pytest.approx(res.best_energy, rel=1e-3), (
        f"battery is slack, so F2 ({obj:.3f}) should equal the B&B optimum "
        f"({res.best_energy:.3f})")
