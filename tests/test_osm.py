"""Reading OpenStreetMap extracts, and the basemap cut from them (roadmap §3.4).

Two things have to hold for a real basemap to be worth having over the invented
one. It must keep what a map needs and drop what it cannot draw -- an extract of
Pontianak carries 193,831 buildings and nobody wants them in a self-contained
HTML file -- and its coordinates must be the instance's own, or the streets will
not line up with the stops.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from drp.geometry.osm import (bbox_around, clip_to_bbox, place_gazetteer,
                              read_osm)
from drp.instances import build_scenario, generate_instance, scenario_template
from drp.instances.geodata import DEFAULT_DATASET, KM_PER_DEGREE_LAT
from drp.viz.basemap import (BASEMAP_SCHEMA, basemap_for_instance,
                             basemap_stats, build_basemap, load_basemap,
                             simplify, write_basemap)

TINY = Path(__file__).resolve().parent / "data" / "tiny.osm"


@pytest.fixture(scope="module")
def tiny():
    return read_osm(TINY)


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------
def test_ways_land_in_the_right_layers(tiny):
    classes = sorted(cls for cls, _ in tiny.roads)
    # trunk -> arterial, tertiary -> secondary, residential -> street,
    # and the second trunk way outside the bounds is still a road.
    assert classes.count("arterial") == 2
    assert classes.count("secondary") == 1
    assert classes.count("street") == 1
    assert len(tiny.waterways) == 1
    assert len(tiny.water_areas) == 1
    assert len(tiny.green) == 1
    assert len(tiny.built) == 1


def test_footways_and_buildings_are_dropped(tiny):
    """Not an oversight: 193,831 building outlines is not a basemap."""
    every_line = ([line for _c, line in tiny.roads] + tiny.waterways
                  + tiny.water_areas + tiny.green + tiny.built)
    # The footway (nodes 1->8) and the building ring would both be 2- and
    # 4-point lines; check by their distinctive coordinates instead.
    footway = [(-0.090, 109.310), (-0.035, 109.315)]
    assert not any(list(line) == footway for line in every_line)
    assert len(every_line) == 8   # 4 roads + river + water area + park + landuse


def test_node_references_are_resolved_to_coordinates(tiny):
    arterials = [line for cls, line in tiny.roads if cls == "arterial"]
    trunk = max(arterials, key=len)
    assert trunk[0] == pytest.approx((-0.090, 109.310))
    assert trunk[-1] == pytest.approx((-0.060, 109.340))
    assert all(isinstance(p, tuple) and len(p) == 2 for p in trunk)


def test_places_need_a_name_and_a_kind(tiny):
    names = sorted(p.name for p in tiny.places)
    assert names == ["Smallwood", "Testville", "Testville"]   # the unnamed one is out


def test_the_gazetteer_prefers_the_larger_place_on_a_name_clash(tiny):
    g = place_gazetteer(tiny)
    assert g["smallwood"] == pytest.approx((-0.070, 109.320))
    # "Testville" is both a city and a suburb; the city wins.
    assert g["testville"] == pytest.approx((-0.050, 109.340))


def test_bounds_are_read(tiny):
    assert tiny.bounds == pytest.approx((-0.10, 109.30, -0.02, 109.38))


def test_a_missing_extract_says_where_to_get_one(tmp_path):
    with pytest.raises(FileNotFoundError, match="overpass"):
        read_osm(tmp_path / "nope.osm")


# ---------------------------------------------------------------------------
# clipping, simplifying, packaging
# ---------------------------------------------------------------------------
def test_clipping_keeps_lines_that_touch_the_box(tiny):
    bbox = (-0.10, 109.30, -0.02, 109.38)
    roads = [line for _c, line in tiny.roads]
    kept = clip_to_bbox(roads, bbox)
    assert len(kept) == 3                 # the far-away trunk way is gone
    assert all(any(bbox[0] <= lat <= bbox[2] for lat, _ in line) for line in kept)


def test_bbox_around_adds_the_margin_in_kilometres():
    bbox = bbox_around([(0.0, 100.0), (0.01, 100.01)], margin_km=1.0)
    grown = (bbox[2] - bbox[0]) - 0.01
    assert grown / 2 == pytest.approx(1.0 / KM_PER_DEGREE_LAT, rel=1e-6)


def test_simplify_drops_collinear_points_and_keeps_corners():
    straight = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0), (0.0, 3.0)]
    assert simplify(straight, 1e-6) == [(0.0, 0.0), (0.0, 3.0)]

    corner = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0)]
    assert simplify(corner, 1e-6) == corner
    assert simplify(corner, 10.0) == [(0.0, 0.0), (1.0, 1.0)]   # tolerance eats it


def test_simplify_survives_a_line_longer_than_the_stack():
    long_line = [(i * 1e-5, math.sin(i) * 1e-5) for i in range(20000)]
    thinned = simplify(long_line, 1e-6)
    assert 2 <= len(thinned) <= len(long_line)


def test_build_basemap_has_every_layer_and_no_stray_geometry(tiny):
    bbox = (-0.10, 109.30, -0.02, 109.38)
    bm = build_basemap(tiny, bbox, simplify_m=1.0)

    assert bm["schema"] == BASEMAP_SCHEMA
    assert set(bm["roads"]) == {"arterial", "secondary", "street"}
    stats = basemap_stats(bm)
    assert stats["arterial"] == 1 and stats["secondary"] == 1 and stats["street"] == 1
    assert stats["water_lines"] == 1 and stats["green"] == 1
    assert stats["places"] == 3
    for lines in bm["roads"].values():
        for line in lines:
            for lat, lon in line:
                assert bbox[0] - 1 <= lat <= bbox[2] + 1


def test_the_street_cap_keeps_the_longest_streets(tiny):
    bm = build_basemap(tiny, (-0.10, 109.30, -0.02, 109.38), max_street_lines=0)
    assert bm["roads"]["street"] == []


def test_basemap_json_round_trips(tmp_path, tiny):
    bm = build_basemap(tiny, (-0.10, 109.30, -0.02, 109.38))
    p = write_basemap(bm, tmp_path / "bm.json")
    assert load_basemap(p)["roads"] == bm["roads"]

    (tmp_path / "bad.json").write_text(json.dumps({"schema": "other/v9"}),
                                       encoding="utf-8")
    with pytest.raises(ValueError, match="basemap schema"):
        load_basemap(tmp_path / "bad.json")


def test_a_planar_instance_has_nowhere_to_put_a_map(tiny):
    inst = generate_instance("planar", 8, 3, seed=2)
    with pytest.raises(ValueError, match="not geodesic"):
        basemap_for_instance(inst, tiny)


@pytest.mark.skipif(not DEFAULT_DATASET.exists(),
                    reason="delivery dataset not present")
def test_the_basemap_covers_the_instance_it_is_built_for(tiny):
    """The margin has to clear the stops, or the map ends mid-frame."""
    inst = build_scenario({**scenario_template(), "nofly": {}})
    bm = basemap_for_instance(inst, tiny)
    min_lat, min_lon, max_lat, max_lon = bm["bounds"]

    for lat, lon in inst.coords:
        assert min_lat < lat < max_lat
        assert min_lon < lon < max_lon

    span = max(max_lat - min_lat, max_lon - min_lon)
    stop_span = max(np.ptp(inst.coords[:, 0]), np.ptp(inst.coords[:, 1]))
    assert span > stop_span * 1.4        # a real margin, not a hairline
