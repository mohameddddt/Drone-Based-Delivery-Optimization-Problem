"""CVRPLIB and Solomon import (roadmap §3.3).

The point of the importer is that an imported file is *the same problem* the
literature solved, so these tests check the semantics, not just the parse:
the depot ends up at node 0 wherever the file put it, the rounded EUC_2D metric
is reproduced, and at ``beta = 0`` this model's energy is exactly the CVRP
distance objective -- which is what makes a published optimum a meaningful
target at all.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from drp.core import Solution, is_feasible, total_energy
from drp.eval.runner import solve_one
from drp.instances import (instance_from_dict, instance_to_dict, read_benchmark,
                           read_cvrplib, read_solomon)

DATA = Path(__file__).resolve().parent / "data"
CVRP_FIXTURE = DATA / "toy-n8-k3.vrp"
SOLOMON_FIXTURE = DATA / "toy-solomon.txt"


# ---------------------------------------------------------------------------
# CVRPLIB
# ---------------------------------------------------------------------------
def test_cvrplib_header_and_shape():
    imported = read_cvrplib(CVRP_FIXTURE)
    inst = imported.instance

    assert inst.name == "toy-n8-k3"
    assert inst.n_customers == 8
    assert inst.n_drones == 3               # from "No of trucks: 3"
    assert inst.payload == pytest.approx(30.0)
    assert math.isinf(inst.battery)         # CVRP has no range limit
    assert inst.beta == 0.0                 # ... and no load term
    assert imported.best_known == pytest.approx(367.0)
    assert imported.best_known_kind == "optimal"
    assert imported.declared_vehicles == 3


def test_depot_moves_to_node_zero_wherever_the_file_puts_it(tmp_path):
    """DEPOT_SECTION may name any node; this model's depot is always node 0."""
    text = "\n".join([
        "NAME : late-depot", "TYPE : CVRP", "DIMENSION : 4",
        "EDGE_WEIGHT_TYPE : EUC_2D", "CAPACITY : 20",
        "NODE_COORD_SECTION",
        " 1 10 10", " 2 20 20", " 3 30 30", " 4 99 99",
        "DEMAND_SECTION",
        " 1 5", " 2 6", " 3 7", " 4 0",
        "DEPOT_SECTION", " 4", " -1", "EOF",
    ])
    p = tmp_path / "late.vrp"
    p.write_text(text, encoding="utf-8")

    inst = read_cvrplib(p).instance
    assert inst.n_customers == 3
    assert np.allclose(inst.coords[0], [99, 99])
    assert np.allclose(inst.coords[1:], [[10, 10], [20, 20], [30, 30]])
    assert np.allclose(inst.demand, [0, 5, 6, 7])   # demands travel with nodes


def test_rounded_euclidean_is_the_metric_the_optimum_is_defined_on():
    rounded = read_cvrplib(CVRP_FIXTURE).instance
    exact = read_cvrplib(CVRP_FIXTURE, round_distances=False).instance

    coords = rounded.coords
    diff = coords[:, None, :] - coords[None, :, :]
    euclid = np.sqrt((diff ** 2).sum(axis=2))

    assert np.allclose(rounded.dist, np.rint(euclid))
    assert np.allclose(exact.dist, euclid)
    assert not np.allclose(rounded.dist, exact.dist)   # the choice matters


def test_dropping_the_rounding_is_recorded_as_a_departure():
    imported = read_cvrplib(CVRP_FIXTURE, round_distances=False)
    assert any("EUC_2D" in note for note in imported.dropped)
    assert any("beta" in note for note in read_cvrplib(CVRP_FIXTURE, beta=0.3).dropped)


def test_at_beta_zero_energy_is_exactly_the_distance_objective():
    inst = read_cvrplib(CVRP_FIXTURE).instance
    sol = Solution([[1, 2, 3], [4, 5], [6, 7, 8]])

    travelled = 0.0
    for route in sol.routes:
        path = [0] + list(route) + [0]
        travelled += sum(inst.dist[a, b] for a, b in zip(path, path[1:]))

    assert total_energy(inst, sol) == pytest.approx(travelled)


def test_branch_and_bound_reproduces_the_files_declared_optimum():
    """Import + solve must land on the value the file claims.

    The fixture's optimum was proved by this repository's own B&B (it is not a
    published figure -- see the file's COMMENT), so this is a regression test on
    the importer's semantics: get the depot, the demands, the capacity or the
    metric wrong and the proved value moves.
    """
    imported = read_cvrplib(CVRP_FIXTURE)
    result = solve_one(imported.instance, "bnb", seed=1, time_limit=60)

    assert result.optimal
    assert result.energy == pytest.approx(imported.best_known)
    assert is_feasible(imported.instance, result.solution)[0]


def test_unsupported_metric_is_refused_not_silently_approximated(tmp_path):
    """An EXPLICIT weight matrix is a different problem, not a rounding detail."""
    text = "\n".join([
        "NAME : odd", "TYPE : CVRP", "DIMENSION : 2",
        "EDGE_WEIGHT_TYPE : EXPLICIT", "CAPACITY : 10",
        "NODE_COORD_SECTION", " 1 0 0", " 2 1 1",
        "DEMAND_SECTION", " 1 0", " 2 3", "DEPOT_SECTION", " 1", " -1", "EOF",
    ])
    p = tmp_path / "odd.vrp"
    p.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="EDGE_WEIGHT_TYPE"):
        read_cvrplib(p)


def test_imported_instance_survives_the_json_format():
    inst = read_cvrplib(CVRP_FIXTURE).instance
    restored = instance_from_dict(instance_to_dict(inst))
    assert restored.round_distances is True
    assert np.allclose(restored.dist, inst.dist)


# ---------------------------------------------------------------------------
# Solomon
# ---------------------------------------------------------------------------
def test_solomon_reads_fleet_and_nodes():
    imported = read_solomon(SOLOMON_FIXTURE)
    inst = imported.instance

    assert inst.n_customers == 10
    assert imported.declared_vehicles == 10
    assert inst.payload == pytest.approx(50.0)
    assert np.allclose(inst.coords[0], [40, 50])       # node 0 is the depot
    assert inst.demand[1:].sum() == pytest.approx(150.0)


def test_solomon_time_windows_are_dropped_loudly_and_kept_aside():
    imported = read_solomon(SOLOMON_FIXTURE)

    assert "time windows" in imported.dropped
    assert len(imported.extras["time_windows"]) == imported.instance.n_customers
    assert imported.extras["depot_window"] == (0.0, 1236.0)


def test_solomon_fleet_is_a_fleet_not_the_declared_ceiling():
    """25 declared vehicles for 25 customers would make partitioning vacuous."""
    imported = read_solomon(SOLOMON_FIXTURE)
    inst = imported.instance

    assert inst.n_drones < imported.declared_vehicles
    assert inst.n_drones * inst.payload >= inst.demand.sum()   # still feasible


def test_solomon_truncates_to_the_standard_reduced_sets():
    imported = read_solomon(SOLOMON_FIXTURE, n_customers=5)
    assert imported.instance.n_customers == 5
    assert imported.instance.name.endswith("-5")


def test_read_benchmark_sniffs_the_format():
    assert read_benchmark(CVRP_FIXTURE).fmt == "cvrplib"
    assert read_benchmark(SOLOMON_FIXTURE).fmt == "solomon"


def test_an_unrecognisable_file_is_an_error(tmp_path):
    p = tmp_path / "nonsense.txt"
    p.write_text("just some prose\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_benchmark(p)
