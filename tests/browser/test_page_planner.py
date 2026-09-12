"""The interactive planner, driven in a headless browser (roadmap §2.1).

`tests/test_server.py` pins the server's request handling. This file drives
the one page of the four that is not a self-contained `file://` document --
it talks to a real, running `drp.app.server` instance over HTTP, the same
way a real browser would.
"""
from __future__ import annotations

import json
import re
import time

import pytest

pytestmark = [pytest.mark.browser, pytest.mark.slow]

DESKTOP = {"width": 1440, "height": 960}
PHONE_WIDTH = 430
READY = '[data-role="depot"]'


def _open(browser, url, viewport=None):
    ctx = browser.new_context(viewport=viewport or DESKTOP, device_scale_factor=1,
                              reduced_motion="reduce")
    page = ctx.new_page()
    console = []
    errors = []
    page.on("console", lambda m: console.append(f"{m.type}: {m.text}")
            if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    # Not under test, and the slowest part of a load if left to the CDN.
    page.route(re.compile(r"fonts\.googleapis\.com/.*"),
               lambda route: route.fulfill(status=200, content_type="text/css", body=""))
    page.route(re.compile(r"fonts\.gstatic\.com/.*"),
               lambda route: route.fulfill(status=200, content_type="font/woff2", body=b""))
    page.goto(url, wait_until="load", timeout=20_000)
    page.wait_for_selector(READY, state="attached", timeout=20_000)
    return ctx, page, console, errors


def _click_fraction(page, fx: float, fy: float) -> None:
    """Click inside the map, at a fraction of its bounding box.

    Avoids reasoning about the SVG viewBox transform: any point that is not
    the exact centre (the depot) lands on empty ground and adds a stop.
    """
    box = page.locator("#map").bounding_box()
    page.mouse.click(box["x"] + box["width"] * fx, box["y"] + box["height"] * fy)


def _read_payload(path, token="DATA"):
    text = path.read_text(encoding="utf-8")
    m = re.search(rf"const {token} = (\{{.*?\}});\n", text, re.S)
    assert m, f"no inlined {token} payload in {path}"
    return json.loads(m.group(1).replace("<\\/", "</"))


# ---------------------------------------------------------------------------
def test_place_stops_solve_and_see_the_replay(planner_server, browser):
    ctx, page, console, errors = _open(browser, planner_server["url"])
    try:
        positions = [(0.15, 0.2), (0.3, 0.75), (0.5, 0.15), (0.7, 0.3),
                     (0.85, 0.6), (0.6, 0.85), (0.25, 0.5), (0.4, 0.35),
                     (0.75, 0.8), (0.15, 0.85)]
        for fx, fy in positions:
            _click_fraction(page, fx, fy)
        assert page.text_content("#stopCount") == str(len(positions))

        page.click("#solveBtn")
        page.wait_for_selector("#loadingOverlay", state="visible", timeout=5_000)
        page.wait_for_selector("#loadingOverlay", state="hidden", timeout=20_000)

        page.wait_for_function(
            "() => !!document.getElementById('flightFrame').getAttribute('src')",
            timeout=5_000)
        src = page.get_attribute("#flightFrame", "src")
        assert src and src.startswith("/results/")
        sid = src.split("/")[2]

        flight_path = planner_server["output_root"] / sid / "flight.html"
        assert flight_path.exists()
        payload = _read_payload(flight_path)
        assert payload["instance"]["n_customers"] == len(positions)

        assert not errors, "uncaught page errors:\n  " + "\n  ".join(errors)
        assert not console, "console errors:\n  " + "\n  ".join(console)
    finally:
        ctx.close()


def test_countdown_shows_real_elapsed_over_the_real_budget(planner_server, browser):
    """No fabricated progress: the number on screen is always elapsed/budget.

    The budget is the server's fixed 5 s ALNS solve, so it must read exactly
    5.0 both times it is sampled; elapsed may only move forward, and by a
    plausible amount for the time actually slept between samples.
    """
    ctx, page, console, errors = _open(browser, planner_server["url"])
    try:
        for fx, fy in [(0.2, 0.2), (0.7, 0.7)]:
            _click_fraction(page, fx, fy)

        page.click("#solveBtn")
        page.wait_for_selector("#loadingOverlay", state="visible", timeout=5_000)

        def sample():
            text = page.text_content("#loadingCountdown")
            m = re.match(r"([\d.]+) / ([\d.]+) s", text.strip())
            assert m, f"unexpected countdown text: {text!r}"
            return float(m.group(1)), float(m.group(2))

        e1, b1 = sample()
        time.sleep(0.6)
        e2, b2 = sample()

        assert b1 == 5.0 and b2 == 5.0
        assert e2 >= e1
        assert e2 - e1 < 3.0  # a real clock tick, not a synthetic jump

        page.wait_for_selector("#loadingOverlay", state="hidden", timeout=20_000)
        assert not errors, "uncaught page errors:\n  " + "\n  ".join(errors)
        assert not console, "console errors:\n  " + "\n  ".join(console)
    finally:
        ctx.close()


def test_infeasible_placement_shows_its_reason(planner_server, browser):
    ctx, page, console, errors = _open(browser, planner_server["url"])
    try:
        _click_fraction(page, 0.3, 0.3)
        _click_fraction(page, 0.7, 0.7)

        # Push the first stop's demand past the fleet's payload capacity --
        # no construction can ever place it, so `solve_one` returns nothing
        # and the server's stop-level diagnostic has to name it.
        demand_input = page.locator(".stop-row input").first
        demand_input.fill("9999")
        demand_input.press("Tab")

        page.click("#solveBtn")
        page.wait_for_selector("#loadingOverlay", state="hidden", timeout=20_000)

        status = page.text_content("#solveStatus")
        assert "payload" in status.lower(), status
        assert "1" in status  # names stop 1
        assert page.get_attribute("#tabsCard", "hidden") is not None

        assert not errors, "uncaught page errors:\n  " + "\n  ".join(errors)
        assert not console, "console errors:\n  " + "\n  ".join(console)
    finally:
        ctx.close()


def test_no_horizontal_overflow_at_430px(planner_server, browser):
    ctx, page, console, errors = _open(
        browser, planner_server["url"],
        viewport={"width": PHONE_WIDTH, "height": 900})
    try:
        for fx, fy in [(0.2, 0.3), (0.6, 0.6), (0.4, 0.8)]:
            _click_fraction(page, fx, fy)
        overflow = page.evaluate(
            "() => document.documentElement.scrollWidth > "
            "document.documentElement.clientWidth + 1")
        assert not overflow

        assert not errors, "uncaught page errors:\n  " + "\n  ".join(errors)
        assert not console, "console errors:\n  " + "\n  ".join(console)
    finally:
        ctx.close()


def test_the_map_draws_actual_terrain_not_a_blank_grid(planner_server, browser):
    """The placement map is not empty ground: a river, roads, blobs of
    built-up land and a district name are all real elements, not a decorative
    flourish bolted on afterwards -- ported from playback_template.html's own
    basemap generator so the placement map and the solved replay read as the
    same city."""
    ctx, page, console, errors = _open(browser, planner_server["url"])
    try:
        ground_children = page.eval_on_selector(
            "#lyrGround", "el => el.childElementCount")
        assert ground_children > 20, (
            f"expected substantial ground-layer geometry, got {ground_children} nodes")

        labels = page.eval_on_selector_all(
            "#lyrGround text", "els => els.map(e => e.textContent)")
        assert len(labels) >= 1, "expected at least one district label"
        # Each label must have been given its own position -- the bug this
        # test is named after left every label stacked at the SVG origin,
        # reading as illegible overlapping text.
        positions = page.eval_on_selector_all(
            "#lyrGround text", "els => els.map(e => [e.getAttribute('x'), e.getAttribute('y')])")
        assert len(set(map(tuple, positions))) == len(positions), (
            f"two labels share a position: {positions}")

        assert not errors, "uncaught page errors:\n  " + "\n  ".join(errors)
        assert not console, "console errors:\n  " + "\n  ".join(console)
    finally:
        ctx.close()


def test_the_city_does_not_reshuffle_as_stops_are_placed(planner_server, browser):
    """The basemap is picked once and stays put while you plan.

    An earlier version reseeded the whole city (river, roads, districts) from
    the current stop count, so it visibly rearranged itself under the user's
    cursor every time a stop was placed or removed -- indistinguishable from
    a bug even though it was deliberate. The fingerprint of the ground layer
    must be identical before and after placing several stops."""
    ctx, page, console, errors = _open(browser, planner_server["url"])
    try:
        fingerprint = lambda: page.eval_on_selector(
            "#lyrGround", "el => el.innerHTML.length + ':' + el.childElementCount")
        before = fingerprint()
        for fx, fy in [(0.15, 0.2), (0.3, 0.75), (0.5, 0.15), (0.7, 0.3), (0.85, 0.6)]:
            _click_fraction(page, fx, fy)
        after_adds = fingerprint()
        removed = page.locator(".stop-row button").first
        removed.click()
        after_remove = fingerprint()

        assert before == after_adds == after_remove

        assert not errors, "uncaught page errors:\n  " + "\n  ".join(errors)
        assert not console, "console errors:\n  " + "\n  ".join(console)
    finally:
        ctx.close()


def test_dragging_the_depot_relocates_it(planner_server, browser):
    """The starting location is not fixed: dragging the hub marker moves it,
    and the moved position is what actually gets solved."""
    ctx, page, console, errors = _open(browser, planner_server["url"])
    try:
        _click_fraction(page, 0.25, 0.25)
        _click_fraction(page, 0.75, 0.75)

        depot_box = page.locator('[data-role="depot"]').bounding_box()
        start_x = depot_box["x"] + depot_box["width"] / 2
        start_y = depot_box["y"] + depot_box["height"] / 2
        map_box = page.locator("#map").bounding_box()
        target_x = map_box["x"] + map_box["width"] * 0.8
        target_y = map_box["y"] + map_box["height"] * 0.2

        page.mouse.move(start_x, start_y)
        page.mouse.down()
        page.mouse.move(target_x, target_y, steps=10)
        page.mouse.up()

        page.click("#solveBtn")
        page.wait_for_selector("#loadingOverlay", state="hidden", timeout=20_000)

        src = page.get_attribute("#flightFrame", "src")
        assert src and src.startswith("/results/")
        sid = src.split("/")[2]
        flight_path = planner_server["output_root"] / sid / "flight.html"
        payload = _read_payload(flight_path)
        moved_depot = payload["instance"]["depot"]
        # Instance space keeps the plane's own coordinates, defaulting to a
        # depot at (50, 50); dragging most of the way to a top-right corner
        # must have moved it well clear of that default in both axes.
        assert abs(moved_depot[0] - 50.0) > 15, moved_depot
        assert abs(moved_depot[1] - 50.0) > 15, moved_depot

        assert not errors, "uncaught page errors:\n  " + "\n  ".join(errors)
        assert not console, "console errors:\n  " + "\n  ".join(console)
    finally:
        ctx.close()


def test_the_embedded_replay_is_not_a_boxed_scrollable_iframe(planner_server, browser):
    """The result pages are full documents, not a panel -- the iframe is
    resized to their real content height rather than clipping them into a
    fixed box with its own internal scrollbar."""
    ctx, page, console, errors = _open(browser, planner_server["url"])
    try:
        for fx, fy in [(0.2, 0.2), (0.7, 0.7)]:
            _click_fraction(page, fx, fy)
        page.click("#solveBtn")
        page.wait_for_selector("#loadingOverlay", state="hidden", timeout=20_000)
        page.wait_for_function(
            "() => !!document.getElementById('flightFrame').getAttribute('src')",
            timeout=5_000)
        # The auto-sizing happens a moment after `load`; give it a beat.
        page.wait_for_timeout(600)

        info = page.evaluate("""() => {
          const f = document.getElementById('flightFrame');
          const doc = f.contentWindow.document;
          return {
            frameHeight: f.getBoundingClientRect().height,
            contentHeight: doc.documentElement.scrollHeight,
          };
        }""")
        # The frame must have grown well past its pre-load placeholder height
        # and must be tall enough to show its content without its own scroll.
        assert info["frameHeight"] > 400, info
        assert info["frameHeight"] >= info["contentHeight"] - 2, info

        assert not errors, "uncaught page errors:\n  " + "\n  ".join(errors)
        assert not console, "console errors:\n  " + "\n  ".join(console)
    finally:
        ctx.close()
