"""Instances built from the real delivery coordinates (roadmap §3.2).

Two things have to hold for a geographic instance to be worth reporting: it must
be *reproducible* (same seed, same instance, and the source CSV never touched),
and its distances must be real kilometres rather than degree arithmetic that
happens to look plausible. Both are checked here, along with the property that
makes the suite usable at all -- every instance has a feasible solution.
"""
from __future__ import annotations

import numpy as np
import pytest

from drp.core import is_feasible
from drp.geometry.distance import haversine_matrix
from drp.instances import (BENCHMARK_SPECS, DEFAULT_DATASET,
                           GEO_BENCHMARK_SPECS, build_geo_instance,
                           district_centroids, filter_points,
                           geo_benchmark_suite, geo_circle_polygon,
                           instance_from_points, load_delivery_points,
                           sample_points)
from drp.instances.geodata import KM_PER_DEGREE_LAT
from drp.meta.construct import best_construction

pytestmark = pytest.mark.skipif(not DEFAULT_DATASET.exists(),
                                reason="delivery dataset not present")


@pytest.fixture(scope="module")
def points():
    return load_delivery_points()


def test_the_dataset_reads_with_its_districts_intact(points):
    assert len(points) == 4360
    districts = {q.district for q in points}
    assert len(districts) == 6
    assert all(d.startswith("Pontianak") for d in districts)
    # Pontianak straddles the equator on the west coast of Borneo.
    assert all(-1.0 < q.lat < 1.0 and 108.0 < q.lon < 110.0 for q in points)


def test_sampling_is_reproducible_and_without_replacement(points):
    pool = filter_points(points, "Pontianak South", "IV")
    a = sample_points(pool, 12, seed=5)
    b = sample_points(pool, 12, seed=5)
    c = sample_points(pool, 12, seed=6)

    assert [q.coord for q in a] == [q.coord for q in b]
    assert [q.coord for q in a] != [q.coord for q in c]
    assert len({q.coord for q in a}) == 12


def test_sampling_does_not_depend_on_the_order_rows_arrive_in(points):
    pool = filter_points(points, "Pontianak East", "III")
    shuffled = list(pool)
    np.random.default_rng(0).shuffle(shuffled)

    assert ([q.coord for q in sample_points(pool, 8, seed=3)]
            == [q.coord for q in sample_points(shuffled, 8, seed=3)])


def test_asking_for_more_points_than_exist_is_an_error(points):
    pool = filter_points(points, "Pontianak South", "IX")
    with pytest.raises(ValueError, match="only"):
        sample_points(pool, len(pool) + 1, seed=1)


def test_distances_are_haversine_kilometres_not_degrees():
    inst = build_geo_instance("geo", 10, 3, seed=11, district="Pontianak City",
                              road_slot="III")

    assert inst.geodesic
    assert np.allclose(inst.dist, haversine_matrix(inst.coords))
    # A city district: every pair is kilometres apart, not hundreds of them.
    off_diagonal = inst.dist[~np.eye(inst.N, dtype=bool)]
    assert 0.0 < off_diagonal.min()
    assert off_diagonal.max() < 25.0


def test_the_depot_defaults_to_the_centroid_of_the_chosen_stops(points):
    chosen = sample_points(filter_points(points, "Pontianak West", "II"), 9,
                           seed=4)
    inst = instance_from_points("geo", chosen, n_drones=3, seed=4)

    assert inst.coords[0] == pytest.approx(
        [np.mean([q.lat for q in chosen]), np.mean([q.lon for q in chosen])])


def test_district_centroids_sit_inside_their_district(points):
    centroids = district_centroids(points)
    assert len(centroids) == 6

    for name, (lat, lon) in centroids.items():
        members = filter_points(points, name)
        assert min(q.lat for q in members) <= lat <= max(q.lat for q in members)
        assert min(q.lon for q in members) <= lon <= max(q.lon for q in members)


def test_a_no_fly_circle_is_circular_on_the_ground_not_in_degree_space():
    """Longitude degrees shrink with latitude; near the equator they barely do,
    so the check that matters is that every vertex is the requested distance
    away when measured with the same haversine metric the solver uses."""
    lat, lon, radius = 51.5, -0.12, 2.0        # London: cos(lat) is far from 1
    poly = geo_circle_polygon(lat, lon, radius, sides=16)

    coords = np.array([(lat, lon)] + [(a, b) for a, b in poly])
    spokes = haversine_matrix(coords)[0, 1:]
    assert spokes == pytest.approx(radius, rel=0.01)

    # The degree-space shape really is wider than it is tall at that latitude.
    height = max(p[0] for p in poly) - min(p[0] for p in poly)
    width = max(p[1] for p in poly) - min(p[1] for p in poly)
    assert width > 1.5 * height
    assert height == pytest.approx(2 * radius / KM_PER_DEGREE_LAT, rel=0.02)


def test_the_geographic_suite_mirrors_the_synthetic_one():
    suite = geo_benchmark_suite()
    assert len(suite) == len(BENCHMARK_SPECS)
    assert ([(i.n_customers, i.n_drones) for i in suite]
            == [(n, k) for _, n, k, _, _ in BENCHMARK_SPECS])
    # every district is represented, so the suite is not one neighbourhood
    assert len({spec[4] for spec in GEO_BENCHMARK_SPECS}) == 6


def test_every_geographic_instance_has_a_feasible_solution():
    """The battery is calibrated, not guessed: a suite nothing can solve, or one
    every route satisfies trivially, would say nothing."""
    for inst in geo_benchmark_suite():
        sol = best_construction(inst)
        assert sol is not None, f"{inst.name}: no feasible construction"
        ok, reason = is_feasible(inst, sol)
        assert ok, f"{inst.name}: {reason}"


def test_the_suite_is_the_same_suite_every_time():
    first, second = geo_benchmark_suite(), geo_benchmark_suite()
    for a, b in zip(first, second):
        assert a.name == b.name
        assert np.allclose(a.coords, b.coords)
        assert np.allclose(a.demand, b.demand)
        assert a.battery == pytest.approx(b.battery)
