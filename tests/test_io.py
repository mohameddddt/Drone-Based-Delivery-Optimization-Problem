"""The instance and solution formats: round-trips and schema conformance."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from drp.core import Solution, is_feasible, total_energy
from drp.instances import (INSTANCE_SCHEMA, SOLUTION_SCHEMA,
                           default_benchmark_suite, generate_instance,
                           generate_zone_instance, instance_from_dict,
                           instance_to_dict, load_instance, load_solution,
                           save_instance, save_solution, solution_to_csv,
                           solution_to_dict, solution_to_geojson)
from drp.meta.construct import best_construction

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "drp" / "instances" / "schema"


@pytest.mark.parametrize("inst", default_benchmark_suite()[:4],
                         ids=lambda i: i.name)
def test_instance_round_trip_preserves_everything(inst):
    restored = instance_from_dict(instance_to_dict(inst))

    assert restored.name == inst.name
    assert restored.n_customers == inst.n_customers
    assert restored.n_drones == inst.n_drones
    assert restored.payload == pytest.approx(inst.payload)
    assert restored.battery == pytest.approx(inst.battery)
    assert restored.alpha == pytest.approx(inst.alpha)
    assert restored.beta == pytest.approx(inst.beta)
    assert restored.nofly_edges == inst.nofly_edges
    assert np.allclose(restored.coords, inst.coords)
    assert np.allclose(restored.demand, inst.demand)
    # and the derived quantity that actually matters
    assert np.allclose(restored.dist, inst.dist)


def test_instance_round_trip_preserves_polygons():
    inst = generate_zone_instance("zio", 8, 3, 99, n_zones=2)
    restored = instance_from_dict(instance_to_dict(inst))
    assert len(restored.nofly_zones) == len(inst.nofly_zones)
    assert np.allclose(restored.dist, inst.dist)


def test_infinite_battery_survives_the_round_trip():
    inst = generate_instance("inf", 6, 2, 5)
    inst.battery = math.inf
    d = instance_to_dict(inst)
    assert d["fleet"]["battery"] is None
    assert math.isinf(instance_from_dict(d).battery)


def test_instance_file_round_trip(tmp_path):
    inst = default_benchmark_suite()[3]
    p = save_instance(inst, tmp_path / "inst.json")
    restored = load_instance(p)
    assert np.allclose(restored.dist, inst.dist)
    assert json.loads(p.read_text(encoding="utf-8"))["schema"] == INSTANCE_SCHEMA


def test_solution_round_trip(tmp_path):
    inst = default_benchmark_suite()[3]
    sol = best_construction(inst)
    assert sol is not None

    p = save_solution(inst, sol, tmp_path / "sol.json", method="greedy")
    restored = load_solution(p, n_drones=inst.n_drones)

    assert restored.used_routes() == sol.used_routes()
    assert total_energy(inst, restored) == pytest.approx(total_energy(inst, sol))


def test_solution_carries_a_verifiable_certificate():
    inst = default_benchmark_suite()[2]
    sol = best_construction(inst)
    d = solution_to_dict(inst, sol, method="greedy")

    assert d["schema"] == SOLUTION_SCHEMA
    cert = d["certificate"]
    assert cert["feasible"] is is_feasible(inst, sol)[0]
    assert cert["total_energy"] == pytest.approx(total_energy(inst, sol))
    # the per-leg energies must add up to the whole
    legs = sum(leg["energy"] for r in d["routes"] for leg in r["legs"])
    assert legs == pytest.approx(cert["total_energy"])


def test_rejects_an_unknown_schema():
    with pytest.raises(ValueError, match="unsupported instance schema"):
        instance_from_dict({"schema": "drp-instance/v99", "customers": [],
                            "depot": [0, 0], "fleet": {"n_drones": 1,
                                                       "payload": 1.0}})


def test_geojson_export_shape():
    inst = default_benchmark_suite()[1]
    sol = best_construction(inst)
    gj = solution_to_geojson(inst, sol)

    assert gj["type"] == "FeatureCollection"
    lines = [f for f in gj["features"] if f["geometry"]["type"] == "LineString"]
    assert len(lines) == len(sol.used_routes())
    for f in lines:
        coords = f["geometry"]["coordinates"]
        assert coords[0] == coords[-1], "each route must start and end at the depot"


def test_csv_export_has_one_row_per_leg():
    inst = default_benchmark_suite()[1]
    sol = best_construction(inst)
    csv = solution_to_csv(inst, sol).strip().splitlines()

    expected = sum(len(r) + 1 for r in sol.used_routes())
    assert len(csv) - 1 == expected


@pytest.mark.parametrize("name", ["drp-instance-v1", "drp-solution-v1",
                                 "drp-scenario-v1"])
def test_schema_files_are_valid_json(name):
    data = json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
    assert data["$schema"].startswith("https://json-schema.org/")
    assert "properties" in data


def test_instance_validates_against_its_json_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((SCHEMA_DIR / "drp-instance-v1.schema.json")
                        .read_text(encoding="utf-8"))
    jsonschema.validate(instance_to_dict(default_benchmark_suite()[0]), schema)


def test_solution_validates_against_its_json_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((SCHEMA_DIR / "drp-solution-v1.schema.json")
                        .read_text(encoding="utf-8"))
    inst = default_benchmark_suite()[0]
    sol = best_construction(inst)
    jsonschema.validate(solution_to_dict(inst, sol, method="greedy"), schema)
