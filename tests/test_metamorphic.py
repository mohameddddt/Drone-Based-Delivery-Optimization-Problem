"""Metamorphic tests: properties that must hold between *related* inputs.

These catch a whole class of bug that golden tests miss, because they check the
model's structure rather than one arithmetic result.
"""
from __future__ import annotations

import math
import random

import numpy as np
import pytest

from drp.core import DRPInstance, route_energy
from drp.instances import generate_instance

SEEDS = [1, 2, 3, 4, 5]


def _rand_route(inst, rng, k=4):
    return rng.sample(range(1, inst.N), min(k, inst.N - 1))


@pytest.mark.parametrize("seed", SEEDS)
def test_reversal_invariant_when_beta_is_zero(seed):
    """With beta = 0 the cost is pure symmetric distance, so reversing a route
    must not change it."""
    inst = generate_instance(f"m{seed}", 8, 3, seed)
    inst.beta = 0.0
    rng = random.Random(seed)
    route = _rand_route(inst, rng)
    assert route_energy(inst, route) == pytest.approx(
        route_energy(inst, route[::-1]))


@pytest.mark.parametrize("seed", SEEDS)
def test_reversal_generally_changes_energy_when_beta_positive(seed):
    """With beta > 0 the carried weight makes the cost order-dependent.

    Not every route changes under reversal (a symmetric layout may not), so this
    asserts the population-level claim: at least one random route differs.
    """
    inst = generate_instance(f"m{seed}", 10, 3, seed)
    assert inst.beta > 0
    rng = random.Random(seed)
    differed = False
    for _ in range(20):
        route = _rand_route(inst, rng, k=5)
        if route_energy(inst, route) != pytest.approx(route_energy(inst, route[::-1])):
            differed = True
            break
    assert differed, "beta > 0 but no route was order-sensitive"


@pytest.mark.parametrize("scale", [0.5, 2.0, 10.0])
def test_scaling_coordinates_scales_energy(scale):
    """Distances are homogeneous of degree 1, and the weight term does not
    depend on scale, so scaling coordinates by c scales energy by exactly c."""
    inst = generate_instance("scale", 8, 3, 42)
    route = [1, 2, 3, 4]
    before = route_energy(inst, route)

    scaled = DRPInstance(
        name="scaled", n_customers=inst.n_customers, n_drones=inst.n_drones,
        coords=inst.coords * scale, demand=inst.demand.copy(),
        battery=math.inf, payload=inst.payload,
        alpha=inst.alpha, beta=inst.beta,
    )
    assert route_energy(scaled, route) == pytest.approx(before * scale)


@pytest.mark.parametrize("seed", SEEDS)
def test_energy_monotone_in_beta(seed):
    """More payload sensitivity can never make a non-empty route cheaper."""
    inst = generate_instance(f"b{seed}", 8, 3, seed)
    route = [1, 2, 3]
    inst.beta = 0.0
    low = route_energy(inst, route)
    inst.beta = 0.6
    high = route_energy(inst, route)
    assert high >= low - 1e-9


def test_zero_demand_makes_beta_irrelevant():
    """If nothing weighs anything, the payload term must vanish."""
    inst = generate_instance("z", 6, 2, 7)
    inst.demand = np.zeros_like(inst.demand)
    route = [1, 2, 3]
    inst.beta = 0.0
    a = route_energy(inst, route)
    inst.beta = 5.0
    b = route_energy(inst, route)
    assert a == pytest.approx(b)
