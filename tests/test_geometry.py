"""Geometry: no-fly polygons and visibility-graph detours (roadmap §4.1).

The claim being tested is the one that makes §4.1 worth doing: a leg blocked by
a zone is not deleted, it is *detoured* -- so its distance grows to the true
shortest obstacle-avoiding path, and the drone still reaches the customer.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from drp.geometry.nofly import (circle_polygon, point_in_polygon, rect_polygon,
                                segment_blocked, segments_properly_cross)
from drp.geometry.visibility import obstacle_distance_matrix, shortest_path

UNIT_SQUARE = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------
def test_point_inside_and_outside():
    assert point_in_polygon((0.5, 0.5), UNIT_SQUARE)
    assert not point_in_polygon((1.5, 0.5), UNIT_SQUARE)
    assert not point_in_polygon((-0.1, 0.5), UNIT_SQUARE)


def test_point_on_boundary_counts_as_outside():
    """A detour path runs along zone boundaries, so touching must be legal."""
    assert not point_in_polygon((0.0, 0.5), UNIT_SQUARE)
    assert not point_in_polygon((0.5, 0.0), UNIT_SQUARE)
    assert not point_in_polygon((0.0, 0.0), UNIT_SQUARE)


def test_segments_properly_cross():
    assert segments_properly_cross((0, 0), (2, 2), (0, 2), (2, 0))
    assert not segments_properly_cross((0, 0), (1, 1), (2, 2), (3, 3))
    # touching at an endpoint is not a proper crossing
    assert not segments_properly_cross((0, 0), (1, 1), (1, 1), (2, 0))


def test_segment_through_polygon_is_blocked():
    assert segment_blocked((-1.0, 0.5), (2.0, 0.5), UNIT_SQUARE)


def test_segment_clear_of_polygon_is_not_blocked():
    assert not segment_blocked((-1.0, 2.0), (2.0, 2.0), UNIT_SQUARE)


def test_segment_along_boundary_is_not_blocked():
    assert not segment_blocked((0.0, 0.0), (1.0, 0.0), UNIT_SQUARE)


def test_segment_wholly_inside_is_blocked():
    assert segment_blocked((0.25, 0.25), (0.75, 0.75), UNIT_SQUARE)


# ---------------------------------------------------------------------------
# Detour distances
# ---------------------------------------------------------------------------
def test_no_zones_gives_plain_euclidean():
    coords = np.array([[0.0, 0.0], [3.0, 4.0], [6.0, 8.0]])
    d = obstacle_distance_matrix(coords, [])
    assert d[0, 1] == pytest.approx(5.0)
    assert d[0, 2] == pytest.approx(10.0)


def test_detour_is_longer_than_the_blocked_straight_line():
    """A wall between two points must lengthen the path, not delete it."""
    coords = np.array([[-2.0, 0.5], [3.0, 0.5]])
    zone = rect_polygon(0.0, -1.0, 1.0, 2.0)   # a wall across the direct route

    straight = 5.0
    d = obstacle_distance_matrix(coords, [zone])

    assert math.isfinite(d[0, 1]), "the customer must still be reachable"
    assert d[0, 1] > straight + 1e-6, "a blocked leg must cost more, not the same"


def test_detour_matches_the_hand_computed_shortest_path():
    """Around a unit square wall the optimal path clips two corners.

    From (-2, 0.5) to (3, 0.5) around the box x in [0,1], y in [0,1]:
    the shortest route goes (-2,0.5) -> (0,0) -> (1,0) -> (3,0.5), because
    passing under the box is shorter than over it.
    """
    coords = np.array([[-2.0, 0.5], [3.0, 0.5]])
    zone = rect_polygon(0.0, 0.0, 1.0, 1.0)

    expected = (math.hypot(2.0, 0.5)   # (-2,0.5) -> (0,0)
                + 1.0                  # (0,0) -> (1,0)
                + math.hypot(2.0, 0.5))  # (1,0) -> (3,0.5)

    d = obstacle_distance_matrix(coords, [zone])
    assert d[0, 1] == pytest.approx(expected, rel=1e-9)


def test_detour_matrix_is_symmetric():
    coords = np.array([[-2.0, 0.5], [3.0, 0.5], [0.5, 4.0]])
    zone = rect_polygon(0.0, 0.0, 1.0, 1.0)
    d = obstacle_distance_matrix(coords, [zone])
    assert np.allclose(d, d.T)


def test_unreachable_point_inside_a_zone():
    """A customer stranded inside a no-fly zone is unreachable, not merely far."""
    coords = np.array([[-2.0, 0.5], [0.5, 0.5]])
    zone = rect_polygon(0.0, 0.0, 1.0, 1.0)
    d = obstacle_distance_matrix(coords, [zone])
    assert math.isinf(d[0, 1])


def test_shortest_path_polyline_avoids_the_zone():
    coords = np.array([[-2.0, 0.5], [3.0, 0.5]])
    zone = rect_polygon(0.0, 0.0, 1.0, 1.0)
    path = shortest_path(coords, [zone], 0, 1)

    assert len(path) > 2, "a blocked leg must bend around the obstacle"
    for a, b in zip(path[:-1], path[1:]):
        assert not segment_blocked(a, b, zone), "the detour re-enters the zone"


# ---------------------------------------------------------------------------
# End to end: zones plug into the solvers with no solver changes
# ---------------------------------------------------------------------------
def test_zone_instance_is_solvable_end_to_end():
    from drp.core import is_feasible
    from drp.eval.runner import solve_one
    from drp.instances import generate_zone_instance

    inst = generate_zone_instance("zone_test", 10, 3, 2026, n_zones=3)
    assert inst.nofly_zones, "the generator produced no zones"

    for method in ("greedy", "ga", "sa", "alns"):
        res = solve_one(inst, method, seed=1, time_limit=2.0)
        assert res.solution is not None, f"{method} returned nothing"
        assert is_feasible(inst, res.solution)[0], f"{method} returned an infeasible plan"


def test_zone_detours_cost_more_than_ignoring_the_zones():
    """Sanity: routing around obstacles is more expensive than pretending they
    are not there. If it were not, the zones would be doing nothing."""
    import numpy as np

    from drp.geometry.distance import euclidean_matrix
    from drp.instances import generate_zone_instance

    inst = generate_zone_instance("zone_cost", 12, 4, 4242, n_zones=3)
    free = euclidean_matrix(inst.coords)
    detoured = inst.dist

    finite = np.isfinite(detoured)
    assert np.all(detoured[finite] >= free[finite] - 1e-9)
    assert np.any(detoured[finite] > free[finite] + 1e-6), \
        "no leg was lengthened, so the zones are not affecting routing at all"
