"""GSAP flight-playback page (roadmap §2.2, web rebuild).

The claim being tested: `build_playback_data` produces geometry consistent with
the rest of the package (same energies, same detour-aware polylines `route_polyline`
already gives the static/animated views), and `render_playback_html` actually
substitutes the template's placeholders rather than just concatenating text.
"""
from __future__ import annotations

import math

from drp.core.energy import route_energy, route_weight
from drp.eval.runner import solve_one
from drp.instances import generate_instance, generate_zone_instance
from drp.viz.webdata import build_playback_data
from drp.viz.webplayback import DATA_TOKEN, NAME_TOKEN, render_playback_html


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
