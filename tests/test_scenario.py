"""The scenario builder (roadmap §3.1).

A scenario is a recipe, so what these tests care about is that the recipe is
followed exactly -- the named depot really is that place, the declared demands
really are those demands, a restricted circle really does lengthen the flights
around it -- and that a mistyped key fails loudly instead of being ignored.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from drp.core import is_feasible
from drp.instances import (DEFAULT_DATASET, build_scenario,
                           build_scenario_file, district_centroids,
                           generate_instance, instance_from_dict,
                           instance_to_dict, load_delivery_points,
                           load_scenario, save_scenario, scenario_template)

needs_dataset = pytest.mark.skipif(not DEFAULT_DATASET.exists(),
                                   reason="delivery dataset not present")


@needs_dataset
def test_the_example_scenario_builds_a_solvable_instance(tmp_path):
    p = save_scenario(scenario_template(), tmp_path / "scenario.json")
    inst = build_scenario_file(p)

    assert inst.n_customers == 20
    assert inst.n_drones == 5
    assert inst.geodesic
    assert len(inst.nofly_zones) == 1
    assert np.isfinite(inst.dist).all()      # the zone detours, never blocks
    assert load_scenario(p)["schema"] == "drp-scenario/v1"


@needs_dataset
def test_a_named_place_resolves_to_that_districts_centroid():
    spec = {"schema": "drp-scenario/v1", "name": "named", "seed": 3,
            "source": {"district": "Pontianak East", "count": 6},
            "depot": {"place": "Pontianak South"},
            "fleet": {"n_drones": 2}}
    inst = build_scenario(spec)

    expected = district_centroids(load_delivery_points())["Pontianak South"]
    assert inst.coords[0] == pytest.approx(expected)


@needs_dataset
def test_an_unknown_place_names_the_ones_that_exist():
    spec = {"schema": "drp-scenario/v1", "seed": 1,
            "source": {"district": "Pontianak East", "count": 4},
            "depot": {"place": "Atlantis"}, "fleet": {"n_drones": 2}}
    with pytest.raises(ValueError, match="Atlantis"):
        build_scenario(spec)


@needs_dataset
def test_the_same_scenario_always_builds_the_same_instance():
    spec = {"schema": "drp-scenario/v1", "name": "repeat", "seed": 17,
            "source": {"district": "Pontianak West", "road_slot": "III",
                       "count": 14},
            "fleet": {"n_drones": 4}}
    a, b = build_scenario(spec), build_scenario(spec)

    assert np.allclose(a.coords, b.coords)
    assert np.allclose(a.demand, b.demand)
    assert a.battery == pytest.approx(b.battery)


def test_a_restricted_circle_lengthens_the_flights_that_cross_it():
    """Four corners with the depot at one of them and a circle in the middle."""
    base = {"schema": "drp-scenario/v1", "name": "zoned", "seed": 21,
            "geodesic": False, "depot": {"coord": [0, 0]},
            "source": {"points": [{"coord": [0, 10], "demand": 1.0},
                                  {"coord": [10, 10], "demand": 1.0},
                                  {"coord": [10, 0], "demand": 1.0}]},
            "fleet": {"n_drones": 2, "payload": 5.0}}
    clear = build_scenario(base)
    zoned = build_scenario({**base, "nofly": {"circles": [
        {"centre": [5, 5], "radius": 2.0, "sides": 16}]}})

    assert len(zoned.nofly_zones) == 1
    assert np.isfinite(zoned.dist).all()               # detoured, never blocked
    assert (zoned.dist >= clear.dist - 1e-9).all()     # a detour never shortens
    # The diagonal depot->far corner is the leg that had to go round.
    assert zoned.dist[0, 2] > clear.dist[0, 2] + 1e-6
    assert zoned.dist[0, 1] == pytest.approx(clear.dist[0, 1])


@needs_dataset
def test_a_zone_drawn_over_a_node_is_refused_not_left_unreachable():
    """Centring the circle on the depot's own place puts the depot inside it."""
    spec = {"schema": "drp-scenario/v1", "name": "buried", "seed": 21,
            "source": {"district": "Pontianak City", "road_slot": "III",
                       "count": 8},
            "depot": {"place": "Pontianak City"}, "fleet": {"n_drones": 3},
            "nofly": {"circles": [{"centre": {"place": "Pontianak City"},
                                   "radius_km": 0.4}]}}
    with pytest.raises(ValueError, match="depot lies inside a restricted zone"):
        build_scenario(spec)


def test_hand_placed_points_keep_their_coordinates_and_demands():
    spec = {"schema": "drp-scenario/v1", "name": "whatif", "seed": 2,
            "source": {"points": [{"coord": [0, 10], "demand": 3.0},
                                  {"coord": [10, 0], "demand": 4.0},
                                  {"coord": [10, 10], "demand": 5.0}]},
            "depot": {"coord": [0, 0]},
            "fleet": {"n_drones": 2, "payload": 9.0},
            "geodesic": False}
    inst = build_scenario(spec)

    assert not inst.geodesic
    assert np.allclose(inst.coords, [[0, 0], [0, 10], [10, 0], [10, 10]])
    assert np.allclose(inst.demand, [0, 3, 4, 5])
    assert inst.payload == pytest.approx(9.0)
    assert inst.dist[0, 3] == pytest.approx(np.hypot(10, 10))   # planar metric


def test_a_payload_that_cannot_lift_the_heaviest_parcel_is_rejected():
    spec = {"schema": "drp-scenario/v1", "seed": 1,
            "source": {"points": [{"coord": [0, 1], "demand": 12.0}]},
            "fleet": {"n_drones": 1, "payload": 5.0}, "geodesic": False}
    with pytest.raises(ValueError, match="payload"):
        build_scenario(spec)


def test_a_synthetic_source_reproduces_the_original_generator():
    spec = {"schema": "drp-scenario/v1", "name": "S1_n5_k2", "seed": 101,
            "source": {"synthetic": {"n": 5}}, "fleet": {"n_drones": 2}}
    built = build_scenario(spec)
    original = generate_instance("S1_n5_k2", 5, 2, 101)

    assert np.allclose(built.coords, original.coords)
    assert np.allclose(built.demand, original.demand)
    assert built.battery == pytest.approx(original.battery)


def test_an_explicit_battery_wins_and_null_means_unbounded():
    base = {"schema": "drp-scenario/v1", "seed": 1, "geodesic": False,
            "source": {"points": [{"coord": [0, 5]}, {"coord": [5, 0]}]},
            "fleet": {"n_drones": 1, "payload": 10.0}}
    assert build_scenario({**base, "fleet": {**base["fleet"],
                                             "battery": 42.0}}).battery == 42.0
    assert np.isinf(build_scenario({**base, "fleet": {**base["fleet"],
                                                      "battery": None}}).battery)


def test_a_mistyped_key_is_refused_rather_than_ignored():
    spec = {"schema": "drp-scenario/v1", "seed": 1,
            "source": {"points": [{"coord": [0, 1]}]},
            "flete": {"n_drones": 3}}
    with pytest.raises(ValueError, match="flete"):
        build_scenario(spec)

    with pytest.raises(ValueError, match="districts"):
        build_scenario({"schema": "drp-scenario/v1",
                        "source": {"districts": "Pontianak South"}})


def test_a_scenario_from_the_future_is_refused():
    with pytest.raises(ValueError, match="drp-scenario/v1"):
        build_scenario({"schema": "drp-scenario/v2", "source": {}})


def test_the_example_scenario_validates_against_its_json_schema():
    jsonschema = pytest.importorskip("jsonschema")
    from pathlib import Path

    schema_dir = (Path(__file__).resolve().parent.parent / "drp" / "instances"
                  / "schema")
    schema = json.loads((schema_dir / "drp-scenario-v1.schema.json")
                        .read_text(encoding="utf-8"))
    jsonschema.validate(scenario_template(), schema)

    # The schema rejects what the builder rejects, rather than drifting from it.
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"schema": "drp-scenario/v1", "flete": {}}, schema)


@needs_dataset
def test_a_built_instance_is_an_ordinary_instance_downstream(tmp_path):
    inst = build_scenario_file(save_scenario(scenario_template(),
                                             tmp_path / "s.json"))
    restored = instance_from_dict(json.loads(json.dumps(instance_to_dict(inst))))

    assert restored.geodesic
    assert np.allclose(restored.dist, inst.dist)

    from drp.meta.construct import best_construction
    sol = best_construction(restored)
    assert sol is not None and is_feasible(restored, sol)[0]
