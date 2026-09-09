"""Golden tests: energies computed by hand, checked against the implementation.

If these break, every number the project has ever produced is wrong, so they use
hand-arithmetic on tiny instances rather than anything derived from the code.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from drp.core import DRPInstance, Solution, route_energy, route_weight, total_energy


def make_instance(**kw) -> DRPInstance:
    """Depot at the origin, three customers on a 3-4-5 friendly layout."""
    defaults = dict(
        name="hand",
        n_customers=3,
        n_drones=2,
        coords=np.array([[0.0, 0.0], [3.0, 4.0], [6.0, 8.0], [0.0, 10.0]]),
        demand=np.array([0.0, 2.0, 3.0, 5.0]),
        battery=math.inf,
        payload=100.0,
        alpha=1.0,
        beta=0.5,
    )
    defaults.update(kw)
    return DRPInstance(**defaults)


def test_single_customer_route_energy():
    """Depot -> c1 -> depot. Out carrying 2 kg, back empty.

    d = 5 each way. Out: 5 * (1 + 0.5*2) = 10. Back: 5 * (1 + 0) = 5. Total 15.
    """
    inst = make_instance()
    assert route_energy(inst, [1]) == pytest.approx(15.0)


def test_two_customer_route_energy_is_order_dependent():
    """The whole point of the model: visiting order changes the cost.

    Route [1, 2]: load 5 kg.
      depot->c1: 5 * (1 + 0.5*5) = 17.5
      c1->c2:    5 * (1 + 0.5*3) = 12.5   (2 kg dropped at c1)
      c2->depot: 10 * (1 + 0)    = 10
      total = 40.0
    """
    inst = make_instance()
    assert route_energy(inst, [1, 2]) == pytest.approx(40.0)
    # The reverse visits the same nodes but carries weight over different legs.
    assert route_energy(inst, [2, 1]) != pytest.approx(40.0)


def test_empty_route_is_free():
    inst = make_instance()
    assert route_energy(inst, []) == 0.0


def test_route_weight_sums_demand():
    inst = make_instance()
    assert route_weight(inst, [1, 2, 3]) == pytest.approx(10.0)


def test_total_energy_sums_routes():
    inst = make_instance()
    sol = Solution([[1], [2]])
    assert total_energy(inst, sol) == pytest.approx(
        route_energy(inst, [1]) + route_energy(inst, [2]))


def test_forbidden_edge_makes_route_infinite():
    inst = make_instance(nofly_edges={(0, 1)})
    assert math.isinf(route_energy(inst, [1]))


def test_beta_zero_reduces_to_distance():
    """With beta = 0 the model collapses to alpha * tour length."""
    inst = make_instance(beta=0.0)
    d = inst.dist
    expected = inst.alpha * (d[0, 1] + d[1, 2] + d[2, 0])
    assert route_energy(inst, [1, 2]) == pytest.approx(expected)
