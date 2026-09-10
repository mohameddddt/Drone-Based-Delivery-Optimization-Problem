"""The interactive flight replay, driven in a headless browser (roadmap §2.5).

`tests/test_viz_web.py` pins the Python half -- one flight per used route,
distances agreeing with `route_energy`, detour-aware polylines. None of it
touches `playback_template.html`, which is where every bug §2.2 records was
found. These tests drive the page.
"""
from __future__ import annotations

import math

import pytest

# `browser` selects them; `slow` keeps them out of `-m "not slow"`, the
# fast subset CI runs on every push, which installs no browser and is
# meant to stay under a couple of minutes.
pytestmark = [pytest.mark.browser, pytest.mark.slow]

READY = ".drone-row"


def seek(h, frac: float) -> None:
    """Scrub the mission timeline to `frac` of its width.

    The timeline sits below the fold at 1440x960, so it has to be scrolled to
    before the pointer coordinates mean anything -- a drag at its unscrolled
    position lands on nothing and the test passes or fails for the wrong
    reason.
    """
    el = h.page.query_selector("#timeline")
    el.scroll_into_view_if_needed()
    h.page.wait_for_timeout(60)
    box = el.bounding_box()
    x = box["x"] + max(1.0, min(box["width"] - 1.0, box["width"] * frac))
    y = box["y"] + box["height"] / 2
    h.page.mouse.move(box["x"] + box["width"] * 0.5, y)
    h.page.mouse.down()
    h.page.mouse.move(x, y)
    h.page.mouse.up()
    h.page.wait_for_timeout(200)


# ---------------------------------------------------------------------------
# it renders at all
# ---------------------------------------------------------------------------
def test_page_renders_and_the_gsap_guard_did_not_fire(open_page, flight_page):
    """The offline guard replaces the whole document, so its absence is the
    check that GSAP loaded and the page built itself."""
    h = open_page(flight_page, READY)
    assert h.page.query_selector(".offline-note") is None
    assert h.page.query_selector("#map") is not None
    assert h.text("#ttl")
    h.assert_clean()


def test_no_uncaught_errors_anywhere_on_load(open_page, flight_page):
    """The regression test for the temporal-dead-zone class of bug.

    §2.4 found three of these on the tree explorer: a `let`/`const` read
    during setup, before its own declaration executed. They throw at load and
    leave a *partly* built page behind, so an element-counting smoke test
    passes and the page is still broken. Only watching `pageerror` catches it.
    Note that `typeof x !== "undefined"` does not guard a TDZ read either --
    `typeof` throws too -- so there is no cheap source-level check to use
    instead of this one.
    """
    h = open_page(flight_page, READY)
    h.assert_clean()


def test_every_used_route_gets_a_manifest_row_and_a_drawn_route(
        open_page, flight_page):
    h = open_page(flight_page, READY)
    n = len(h.data["flights"])
    assert n > 0
    assert h.page.eval_on_selector_all(".drone-row", "els => els.length") == n
    assert h.page.eval_on_selector_all(
        "#lyrRoutes > g", "els => els.length") == n
    assert h.page.eval_on_selector_all(
        "#lyrDrones > g", "els => els.length") == n
    h.assert_clean()


def test_every_customer_gets_a_stop_symbol(open_page, flight_page):
    h = open_page(flight_page, READY)
    n_customers = h.data["instance"]["n_customers"]
    assert h.page.eval_on_selector_all(
        "#lyrStops > g", "els => els.length") == n_customers
    h.assert_clean()


def test_panels_are_populated_not_empty_shells(open_page, flight_page):
    """The GSAP guard is not the only way to get an empty page -- a throw part
    way through leaves panels that exist and say nothing."""
    h = open_page(flight_page, READY)
    assert len(h.text("#solutionKv")) > 40
    assert h.text("#log")
    assert h.text("#rdDist")
    h.assert_clean()


# ---------------------------------------------------------------------------
# the numbers on the page are the numbers in the payload
# ---------------------------------------------------------------------------
def test_header_stats_match_the_payload(open_page, flight_page):
    h = open_page(flight_page, READY)
    data = h.data
    assert h.numbers("#stDrones")[0] == len(data["flights"])
    assert h.numbers("#stZones")[0] == len(data["meta"]["zones"])
    delivered, total = h.numbers("#stDeliv")
    assert delivered == 0, "the replay opens before anything has been delivered"
    assert total == data["instance"]["n_customers"]
    h.assert_clean()


def test_solver_panel_reports_the_payloads_objective_and_separation(
        open_page, flight_page):
    """`--separation` is the most misreadable number on the page, so it has to
    be the one the payload carries, not a second default computed in JS."""
    h = open_page(flight_page, READY)
    shown = h.numbers("#solutionKv")
    energy = h.data["solution"]["certificate"]["total_energy"]
    sep = h.data["meta"]["separation"]
    assert any(math.isclose(v, round(energy, 1), abs_tol=0.15) for v in shown), \
        f"objective {energy:.1f} not among the solver panel's numbers {shown}"
    assert any(math.isclose(v, round(sep, 1), abs_tol=0.05) for v in shown), \
        f"separation {sep:.1f} not among the solver panel's numbers {shown}"
    h.assert_clean()


def test_manifest_rows_report_each_routes_own_energy_and_payload(
        open_page, flight_page):
    """The §2.2 lookup bug: `rows[f.drone]` assumed array index == drone id,
    which only holds when every drone flies. Reading each row's numbers back
    against the flight of that id is what would have caught it."""
    h = open_page(flight_page, READY)
    rows = h.page.eval_on_selector_all(
        ".drone-row",
        """els => els.map(e => ({
             name: e.querySelector('.name').textContent.trim(),
             text: e.textContent.replace(/\\s+/g, ' ')}))""")
    assert len(rows) == len(h.data["flights"])
    for row, f in zip(rows, h.data["flights"]):
        assert row["name"] == f"DRONE {f['drone']}"
        assert f"{f['payload']:.1f}kg" in row["text"]
        assert f"{f['energy']:.0f}" in row["text"]
    h.assert_clean()


def test_total_flown_distance_matches_the_longest_flight(open_page, flight_page):
    """The transport readout is `flown / total`, and `total` is the clock's
    length -- the longest single flight, since the fleet flies concurrently."""
    h = open_page(flight_page, READY)
    flown, total = h.numbers("#rdDist")
    assert flown == 0.0
    longest = max(f["length"] for f in h.data["flights"])
    assert math.isclose(total, round(longest, 1), abs_tol=0.15)
    h.assert_clean()


# ---------------------------------------------------------------------------
# the controls do what they claim
# ---------------------------------------------------------------------------
def test_play_advances_the_clock(open_page, flight_page):
    h = open_page(flight_page, READY)
    before = h.numbers("#rdDist")[0]
    h.page.click("#playBtn")
    h.page.wait_for_function(
        """(before) => {
             const t = document.getElementById("rdDist").textContent;
             return parseFloat(t.split("/")[0]) > before;
           }""", arg=before, timeout=5000)
    h.page.click("#playBtn")          # pause again
    assert h.numbers("#rdDist")[0] > before
    h.assert_clean()


def test_space_toggles_play(open_page, flight_page):
    h = open_page(flight_page, READY)
    before = h.numbers("#rdDist")[0]
    h.page.keyboard.press("Space")
    h.page.wait_for_function(
        """(before) => parseFloat(document.getElementById("rdDist")
             .textContent.split("/")[0]) > before""", arg=before, timeout=5000)
    h.page.keyboard.press("Space")
    h.assert_clean()


def test_scrubbing_the_timeline_seeks(open_page, flight_page):
    """Dragging anywhere on the timeline seeks; seeking to the end must land on
    the end of the clock, not somewhere near it."""
    h = open_page(flight_page, READY)
    seek(h, 1.0)
    flown, total = h.numbers("#rdDist")
    assert flown > 0.9 * total, f"seek to the end left the clock at {flown}/{total}"
    h.assert_clean()


def test_seeking_to_the_end_delivers_everything(open_page, flight_page):
    """A feasible solution serves every customer, so the end of the replay must
    show every stop delivered. This is the assertion that would have caught the
    §2.2 bug where deliveries fired off `sum(leg.distance)` instead of the flown
    polyline: with a detour, the count went wrong."""
    h = open_page(flight_page, READY)
    seek(h, 1.0)
    delivered, total = h.numbers("#stDeliv")
    assert delivered == total == h.data["instance"]["n_customers"]
    h.assert_clean()


def test_seeking_backwards_un_fires_events(open_page, flight_page):
    """"Seeking backwards un-fires events, so the replay stays a replay
    instead of an ever-growing tally" -- `docs/VISUALISATION.md`. Nothing
    enforced that claim before this test."""
    h = open_page(flight_page, READY)
    seek(h, 1.0)
    assert h.numbers("#stDeliv")[0] > 0
    seek(h, 0.0)
    assert h.numbers("#stDeliv")[0] == 0, "seeking back to 0 left deliveries fired"
    h.assert_clean()


def test_selecting_a_drone_opens_why_this_route(open_page, flight_page):
    h = open_page(flight_page, READY)
    assert h.page.is_hidden("#whyPanel"), "the panel should start hidden"
    h.page.click(".drone-row")
    h.page.wait_for_selector("#whyPanel .kv, #whyPanel *", state="attached")
    h.page.wait_for_timeout(150)
    why = h.text("#whyPanel")
    assert "Why this route" in why
    first = h.data["flights"][0]
    assert f"drone {first['drone']}" in why
    assert h.page.eval_on_selector_all(".drone-row.hot", "els => els.length") == 1
    h.assert_clean()


def test_why_this_route_reports_that_flights_own_numbers(open_page, flight_page):
    """Not just "a panel opened" -- the panel must be about the drone clicked."""
    h = open_page(flight_page, READY)
    rows = h.page.query_selector_all(".drone-row")
    target = h.data["flights"][-1]
    rows[-1].click()
    h.page.wait_for_timeout(200)
    why = h.text("#whyPanel")
    assert f"{target['energy']:.0f}" in why
    assert f"{target['payload']:.1f}" in why
    assert f"{target['length']:.1f}" in why, \
        "the flown distance must be the polyline length, not the sum of legs"
    h.assert_clean()


def test_clicking_the_selected_row_again_deselects(open_page, flight_page):
    h = open_page(flight_page, READY)
    h.page.click(".drone-row")
    h.page.wait_for_timeout(150)
    assert h.page.eval_on_selector_all(".drone-row.hot", "els => els.length") == 1
    h.page.click(".drone-row")
    h.page.wait_for_timeout(150)
    assert h.page.eval_on_selector_all(".drone-row.hot", "els => els.length") == 0
    assert h.page.is_hidden("#whyPanel")
    h.assert_clean()


def test_zoom_controls_change_the_camera(open_page, flight_page):
    h = open_page(flight_page, READY)
    before = h.text(".plate .zoom, #readout") or h.text("#readout")
    h.page.click("#zIn")
    h.page.wait_for_timeout(200)
    after = h.text("#readout")
    assert after != before, f"zoom in left the readout at {before!r}"
    h.page.click("#zRst")
    h.page.wait_for_timeout(200)
    assert h.text("#readout") == before
    h.assert_clean()


# ---------------------------------------------------------------------------
# layout
# ---------------------------------------------------------------------------
def test_no_horizontal_overflow_at_430px(open_page, flight_page):
    """The §2.2 layout bug was the other direction -- `aspect-ratio` on a
    stretched grid row fed the map's *height* back into its *width* until it
    covered the rail -- but the check that catches both is the same one."""
    h = open_page(flight_page, READY)
    h.phone()
    assert not h.has_horizontal_overflow(), \
        "page scrolls sideways at 430px: " + "; ".join(h.overflowing_elements())
    h.assert_clean()


def test_no_horizontal_overflow_at_430px_after_selecting_a_drone(
        open_page, flight_page):
    """Selecting opens the "why this route" panel, which is the widest thing
    the rail ever holds -- a per-leg table. Checking the empty layout only
    would miss it."""
    h = open_page(flight_page, READY)
    h.phone()
    h.page.click(".drone-row")
    h.page.wait_for_timeout(250)
    assert not h.has_horizontal_overflow(), \
        "why-this-route overflows at 430px: " + "; ".join(h.overflowing_elements())
    h.assert_clean()


def test_the_rail_is_height_bound_to_the_map_on_desktop(open_page, flight_page):
    """§2.2's third bug: the map painted over the rail because the two were
    not height-bound. The rail now takes its max height from the map panel."""
    h = open_page(flight_page, READY)
    # `#rail` is the scrolling list inside the panel; `.rail` is the panel the
    # height is bound on. Binding the wrong one is exactly how the map came to
    # paint over the manifest in the first place.
    map_h, rail_max = h.page.evaluate(
        """() => [document.getElementById("mapPanel").offsetHeight,
                  document.querySelector(".rail").style.maxHeight]""")
    assert rail_max == f"{map_h}px"
    h.assert_clean()


# ---------------------------------------------------------------------------
# the theme reaches the page
# ---------------------------------------------------------------------------
def test_route_strokes_use_the_payloads_colours(open_page, flight_page):
    """The palette lives in Python. If the page ever grew a copy of its own,
    the two would drift apart silently; this notices."""
    h = open_page(flight_page, READY)
    strokes = h.page.eval_on_selector_all(
        "#lyrRoutes > g",
        """els => els.map(g => g.children[1].getAttribute("stroke"))""")
    assert strokes == [f["color"] for f in h.data["flights"]]
    h.assert_clean()


def test_each_route_carries_its_own_dash_pattern(open_page, flight_page):
    """The second channel (roadmap §2.5): colour is never the only carrier of
    which route is which, so two routes must never share a dash pattern."""
    h = open_page(flight_page, READY)
    dashes = h.page.eval_on_selector_all(
        "#lyrRoutes > g",
        """els => els.map(g => g.children[1].getAttribute("stroke-dasharray"))""")
    assert all(d for d in dashes)
    assert len(set(dashes)) == len(dashes), f"two routes share a dash: {dashes}"
    h.assert_clean()


def test_theme_tokens_reach_the_css_custom_properties(open_page, flight_page):
    """The stylesheet and the SVG have to agree, which they only do because the
    tokens are pushed into the custom properties at startup."""
    h = open_page(flight_page, READY)
    tokens = h.data["theme"]["tokens"]
    got = h.page.evaluate(
        """() => {
             const s = getComputedStyle(document.documentElement);
             return {restricted: s.getPropertyValue("--restricted").trim(),
                     caution: s.getPropertyValue("--caution").trim(),
                     success: s.getPropertyValue("--success").trim()};
           }""")
    assert got["restricted"] == tokens["restricted"]
    assert got["caution"] == tokens["caution"]
    assert got["success"] == tokens["success"]
    h.assert_clean()


# ---------------------------------------------------------------------------
# reduced motion
# ---------------------------------------------------------------------------
def test_the_page_settles_the_same_way_with_motion_enabled(
        open_page, flight_page):
    """Every other test here runs under `prefers-reduced-motion: reduce`, which
    is what makes them deterministic. That is only legitimate if the animated
    path reaches the same place, so this one waits for the intro to finish and
    compares."""
    h = open_page(flight_page, READY, motion="no-preference")
    h.page.wait_for_function(
        """() => [...document.querySelectorAll(".drone-row")]
                 .every(r => parseFloat(getComputedStyle(r).opacity) > 0.99)""",
        timeout=10_000)
    assert h.page.eval_on_selector_all(
        ".drone-row", "els => els.length") == len(h.data["flights"])
    assert h.numbers("#stDrones")[0] == len(h.data["flights"])
    h.assert_clean()
