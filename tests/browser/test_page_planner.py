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
