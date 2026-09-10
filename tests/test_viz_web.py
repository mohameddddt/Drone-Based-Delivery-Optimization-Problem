"""GSAP flight-playback page (roadmap §2.2, web rebuild).

The claim being tested: `build_playback_data` produces geometry consistent with
the rest of the package (same energies, same detour-aware polylines `route_polyline`
already gives the static/animated views), and `render_playback_html` actually
substitutes the template's placeholders rather than just concatenating text.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from drp.core.energy import route_energy, route_weight
from drp.eval.runner import solve_one
from drp.instances import (DEFAULT_DATASET, build_geo_instance,
                           generate_instance, generate_zone_instance)
from drp.viz.webdata import build_playback_data
from drp.viz.webplayback import DATA_TOKEN, NAME_TOKEN, render_playback_html


@pytest.fixture(scope="module")
def geo_instance():
    if not DEFAULT_DATASET.exists():
        pytest.skip("delivery dataset not present")
    return build_geo_instance("web-geo", 9, 3, seed=12,
                              district="Pontianak South", road_slot="IV")


def _solved(inst):
    res = solve_one(inst, "greedy", seed=1, time_limit=1.0)
    assert res.solution is not None
    return res.solution


def test_playback_data_has_one_flight_per_used_route():
    inst = generate_instance("plain", 8, 3, seed=1)
    sol = _solved(inst)
    data = build_playback_data(inst, sol)
    assert len(data["flights"]) == len(sol.used_routes())
    assert {f["drone"] for f in data["flights"]} == {k for k, r in enumerate(sol.routes) if r}


def test_playback_data_cumulative_matches_length_and_energy():
    inst = generate_instance("plain", 8, 3, seed=1)
    sol = _solved(inst)
    data = build_playback_data(inst, sol)
    for f in data["flights"]:
        cum = f["cumulative"]
        assert cum == sorted(cum), "cumulative distance must be non-decreasing"
        assert math.isclose(cum[-1], f["length"], rel_tol=1e-9)
        route = f["route"]
        assert math.isclose(f["energy"], route_energy(inst, route), rel_tol=1e-9)
        assert math.isclose(f["payload"], route_weight(inst, route), rel_tol=1e-9)


def test_playback_data_polyline_detours_around_nofly_zones():
    """The web view must fly the same path the static/animated views do -- it
    reuses `route_polyline`, so a route crossing a zone should bend around it,
    not cut through."""
    inst = generate_zone_instance("zone", 10, 3, seed=2026, n_zones=3)
    sol = _solved(inst)
    data = build_playback_data(inst, sol)
    assert data["meta"]["zones"], "the generator produced no zones"
    # every flight's polyline waypoint count is at least the direct-hop count;
    # a detour inserts extra vertices around any blocked leg.
    for f in data["flights"]:
        assert len(f["polyline"]) >= len(f["route"]) + 2


def test_playback_data_separation_defaults_to_three_percent_of_span():
    """Must agree with `drp.viz.animate.animate_routes`'s default so the GIF and
    the web page flag the same conflicts."""
    import numpy as np

    inst = generate_instance("plain", 8, 3, seed=1)
    sol = _solved(inst)
    data = build_playback_data(inst, sol)
    co = inst.coords
    span = max(float(np.ptp(co[:, 0])), float(np.ptp(co[:, 1])))
    assert math.isclose(data["meta"]["separation"], 0.03 * span, rel_tol=1e-9)


def test_render_playback_html_substitutes_both_placeholders(tmp_path):
    inst = generate_instance("plain", 6, 2, seed=3)
    sol = _solved(inst)
    out = render_playback_html(inst, sol, tmp_path / "flight.html")

    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert DATA_TOKEN not in text
    assert NAME_TOKEN not in text
    assert "<script" in text
    assert '"name": "plain"' in text
    assert f'"n_drones": {inst.n_drones}' in text


def test_render_playback_html_end_to_end_smoke(tmp_path):
    inst = generate_zone_instance("smoke", 10, 3, seed=99, n_zones=2)
    sol = _solved(inst)
    out = render_playback_html(inst, sol, tmp_path / "sub" / "flight.html")
    assert out.stat().st_size > 10_000


# ---------------------------------------------------------------------------
# geodesic instances (roadmap §3.2/§3.4)
#
# The page was built before any instance had real coordinates. Handed (lat, lon)
# it would draw latitude along x -- north pointing right -- and measure flights
# in degrees, a unit that is neither kilometres nor consistent between the two
# axes. `projection` is what stops both, so it is what these pin.
# ---------------------------------------------------------------------------
def test_a_planar_instance_needs_no_projection():
    inst = generate_instance("plain", 8, 3, seed=1)
    data = build_playback_data(inst, _solved(inst))
    assert data["meta"]["projection"] is None
    assert data["meta"]["units"] == "units"


def test_a_geodesic_instance_is_projected_to_kilometres(geo_instance):
    inst = geo_instance
    data = build_playback_data(inst, _solved(inst))
    proj = data["meta"]["projection"]

    assert proj["kind"] == "geodesic"
    assert data["meta"]["units"] == "km"
    assert (proj["lat0"], proj["lon0"]) == (inst.coords[0][0], inst.coords[0][1])
    # Longitude degrees shrink with latitude; near the equator, barely.
    assert proj["km_per_deg_lon"] == pytest.approx(
        proj["km_per_deg_lat"] * math.cos(math.radians(proj["lat0"])))


def test_flown_distance_is_kilometres_not_degrees(geo_instance):
    """The page's "flown distance" has to be the same kind of number the
    solver's energies are, or the two panels quietly disagree."""
    inst = geo_instance
    sol = _solved(inst)
    data = build_playback_data(inst, sol)

    for flight in data["flights"]:
        route = flight["route"]
        straight = sum(inst.dist[a, b] for a, b in
                       zip([0] + route, route + [0]))
        # Flown >= straight-line (detours only add), and within a factor that a
        # degree-based measurement would blow past by ~100x.
        assert flight["length"] >= straight - 1e-6
        assert flight["length"] < straight * 1.5 + 1e-6
        assert flight["length"] < 1000.0          # km, over a single city


def test_separation_is_expressed_in_the_units_the_page_measures(geo_instance):
    inst = geo_instance
    data = build_playback_data(inst, _solved(inst))
    from drp.geometry.distance import KM_PER_DEGREE
    span_km = (max(np.ptp(inst.coords[:, 0]), np.ptp(inst.coords[:, 1]))
               * KM_PER_DEGREE)
    assert data["meta"]["separation"] == pytest.approx(0.03 * span_km, rel=0.02)


def test_a_basemap_travels_with_the_payload_and_into_the_page(tmp_path,
                                                              geo_instance):
    from drp.geometry.osm import read_osm
    from drp.viz.basemap import basemap_for_instance

    inst = geo_instance
    osm = read_osm(Path(__file__).resolve().parent / "data" / "tiny.osm")
    basemap = basemap_for_instance(inst, osm)

    data = build_playback_data(inst, _solved(inst), basemap=basemap)
    assert data["basemap"]["schema"] == "drp-basemap/v1"

    page = render_playback_html(inst, _solved(inst), tmp_path / "p.html",
                                basemap=basemap).read_text(encoding="utf-8")
    assert '"drp-basemap/v1"' in page
    # and the page must be told to draw it rather than its invented city
    assert "drawRealBasemap" in page


def test_without_a_basemap_the_page_still_invents_one(tmp_path, geo_instance):
    page = render_playback_html(geo_instance, _solved(geo_instance),
                                tmp_path / "p.html").read_text(encoding="utf-8")
    assert '"drp-basemap/v1"' not in page
    assert "REALMAP" in page          # the branch exists; it just takes the other arm
