"""QGroundControl mission export (roadmap §3.5).

A ``.plan`` file is the point where this project stops being a study and starts
being something a ground station can fly, so the tests check the two things that
would make an exported mission wrong rather than merely ugly: the waypoints are
the solved route in the solved order, and a planar instance -- whose coordinates
mean nothing on Earth -- cannot be exported without saying where it is.
"""
from __future__ import annotations

import json
import math

import numpy as np
import pytest

from drp.core import Solution
from drp.core.energy import route_energy, route_weight
from drp.geometry.distance import haversine_matrix
from drp.instances import (Anchor, DEFAULT_DATASET, build_geo_instance,
                           generate_instance, generate_zone_instance,
                           mission_summary, route_to_qgc_plan,
                           solution_to_qgc_plans, write_qgc_plans)
from drp.instances.qgc import (MAV_CMD_NAV_LAND, MAV_CMD_NAV_TAKEOFF,
                               MAV_CMD_NAV_WAYPOINT)

needs_dataset = pytest.mark.skipif(not DEFAULT_DATASET.exists(),
                                   reason="delivery dataset not present")


@pytest.fixture
def geo_instance():
    return build_geo_instance("mission", 9, 3, seed=7,
                              district="Pontianak South", road_slot="IV")


@needs_dataset
def test_a_mission_is_take_off_every_stop_return_land(geo_instance):
    route = [3, 1, 5]
    plan = route_to_qgc_plan(geo_instance, route)
    items = plan["mission"]["items"]

    assert plan["fileType"] == "Plan"
    assert [i["command"] for i in items] == [
        MAV_CMD_NAV_TAKEOFF, *[MAV_CMD_NAV_WAYPOINT] * (len(route) + 1),
        MAV_CMD_NAV_LAND]
    assert [i["doJumpId"] for i in items] == list(range(1, len(items) + 1))
    assert all(i["type"] == "SimpleItem" for i in items)
    assert all(i["autoContinue"] for i in items)


@needs_dataset
def test_the_waypoints_are_the_solved_route_in_order(geo_instance):
    route = [4, 2, 8, 6]
    items = route_to_qgc_plan(geo_instance, route)["mission"]["items"]
    flown = [(item["params"][4], item["params"][5]) for item in items]

    expected = [tuple(geo_instance.coords[0])]
    expected += [tuple(geo_instance.coords[c]) for c in route]
    expected += [tuple(geo_instance.coords[0])] * 2      # return, then land
    assert flown == pytest.approx(expected)
    assert items[0]["Altitude"] == 60.0
    assert items[-1]["params"][6] == 0.0                 # land at ground level


@needs_dataset
def test_the_home_position_is_the_depot(geo_instance):
    plan = route_to_qgc_plan(geo_instance, [1, 2])
    assert plan["mission"]["plannedHomePosition"][:2] == pytest.approx(
        list(geo_instance.coords[0]))


def test_a_planar_instance_cannot_be_exported_without_saying_where_it_is():
    inst = generate_instance("planar", 6, 2, seed=3)
    with pytest.raises(ValueError, match="anchor"):
        route_to_qgc_plan(inst, [1, 2])


def test_the_anchor_projects_instance_units_into_real_metres():
    """One unit at the default anchor scale is 100 m, checked with haversine."""
    inst = generate_instance("planar", 6, 2, seed=3)
    inst.coords[0] = [0.0, 0.0]
    inst.coords[1] = [0.0, 10.0]        # 10 units north = 1 km
    inst.coords[2] = [10.0, 0.0]        # 10 units east  = 1 km
    inst.invalidate_distances()

    anchor = Anchor(lat=-0.05, lon=109.33, metres_per_unit=100.0)
    items = route_to_qgc_plan(inst, [1, 2], anchor=anchor)["mission"]["items"]
    home = (items[0]["params"][4], items[0]["params"][5])
    north = (items[1]["params"][4], items[1]["params"][5])
    east = (items[2]["params"][4], items[2]["params"][5])

    assert home == pytest.approx((anchor.lat, anchor.lon))
    spans = haversine_matrix(np.array([home, north, east]))
    assert spans[0, 1] == pytest.approx(1.0, rel=0.01)     # km
    assert spans[0, 2] == pytest.approx(1.0, rel=0.01)
    assert north[0] > home[0] and east[1] > home[1]        # north-east, not swapped


def test_restricted_zones_become_exclusion_geofences():
    inst = generate_zone_instance("zoned", 8, 3, seed=5, n_zones=2)
    anchor = Anchor(lat=51.5, lon=-0.12, metres_per_unit=50.0)
    plan = route_to_qgc_plan(inst, [1, 2, 3], anchor=anchor)

    fences = plan["geoFence"]["polygons"]
    assert len(fences) == len(inst.nofly_zones)
    assert all(f["inclusion"] is False for f in fences)
    assert all(len(f["polygon"]) == len(z)
               for f, z in zip(fences, inst.nofly_zones))
    assert all(-90 <= lat <= 90 and -180 <= lon <= 180
               for f in fences for lat, lon in f["polygon"])


@needs_dataset
def test_one_file_per_flying_drone(tmp_path, geo_instance):
    sol = Solution([[1, 2, 3], [], [4, 5, 6, 7, 8, 9]])
    written = write_qgc_plans(geo_instance, sol, tmp_path / "missions")

    assert len(written) == 2                       # the idle drone gets no plan
    assert set(solution_to_qgc_plans(geo_instance, sol)) == {0, 2}
    for path in written:
        plan = json.loads(path.read_text(encoding="utf-8"))
        assert plan["mission"]["items"]            # each parses as JSON


@needs_dataset
def test_a_single_plan_file_is_refused_for_a_fleet(tmp_path, geo_instance):
    two = Solution([[1, 2], [3, 4]])
    with pytest.raises(ValueError, match="one vehicle"):
        write_qgc_plans(geo_instance, two, tmp_path / "fleet.plan")

    one = Solution([[1, 2, 3]])
    assert write_qgc_plans(geo_instance, one, tmp_path / "solo.plan") == [
        tmp_path / "solo.plan"]


@needs_dataset
def test_an_empty_route_is_not_a_mission(geo_instance):
    with pytest.raises(ValueError):
        route_to_qgc_plan(geo_instance, [])
    with pytest.raises(ValueError, match="no non-empty route"):
        write_qgc_plans(geo_instance, Solution([[], []]), "unused")


@needs_dataset
def test_the_summary_reports_exactly_what_the_plan_cannot_carry(geo_instance):
    sol = Solution([[1, 2, 3], [], [4, 5]])
    rows = mission_summary(geo_instance, sol)

    assert [r["drone"] for r in rows] == [0, 2]
    for row, route in zip(rows, [[1, 2, 3], [4, 5]]):
        assert row["stops"] == len(route)
        assert row["energy"] == pytest.approx(route_energy(geo_instance, route))
        assert row["payload_at_departure"] == pytest.approx(
            route_weight(geo_instance, route))
        assert row["units"] == "km"
        assert row["battery_limit"] == pytest.approx(geo_instance.battery)


def test_an_unbounded_battery_is_reported_as_such():
    inst = generate_instance("planar", 5, 2, seed=1)
    inst.battery = math.inf
    assert mission_summary(inst, Solution([[1, 2]]))[0]["battery_limit"] is None
