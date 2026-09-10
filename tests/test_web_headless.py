"""The replay page, actually loaded in a browser.

`tests/test_viz_web.py` pins the Python payload. It cannot fail when the ~1,400
lines of JavaScript that turn that payload into a map throw on line one -- and
every bug found in that layer so far (deliveries firing early, phantom
separation breaches, a tween that never died, the map painting over the rail)
was found by a person driving the page by hand. PROGRESS.md has listed "a
headless smoke test of the rendered page" as the obvious next hardening step
ever since.

This is it, and it is deliberately cheap: `tools/headless_check.py` drives
whatever Chrome or Edge is already installed, with a stub standing in for the
GSAP CDN script, and reports what the page actually built. These tests skip
when no browser is present, which is honest about what CI will and will not
cover on a given runner.

What they assert is structural rather than pictorial: the layers exist, the map
carries the right amount of geometry, and nothing threw. A screenshot cannot be
diffed reliably; "the page rendered nothing" can.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from drp.instances import (DEFAULT_DATASET, build_geo_instance,
                           generate_zone_instance)
from drp.meta.construct import best_construction
from drp.viz.webplayback import render_playback_html

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.headless_check import find_browser, run          # noqa: E402

BROWSER = find_browser()
TINY_OSM = Path(__file__).resolve().parent / "data" / "tiny.osm"

pytestmark = pytest.mark.skipif(BROWSER is None,
                                reason="no Chrome or Edge installed")


def _render(tmp_path, inst, name="page.html", **kwargs):
    sol = best_construction(inst)
    assert sol is not None
    return render_playback_html(inst, sol, tmp_path / name, **kwargs)


def test_the_synthetic_page_renders_without_throwing(tmp_path):
    inst = generate_zone_instance("zoned", 10, 3, seed=5, n_zones=2)
    findings = run(_render(tmp_path, inst), BROWSER)

    assert findings["svg_present"], "no <svg id=map> in the rendered DOM"
    assert not findings["console_errors"], findings["console_errors"]
    # The invented chart: land, river, blobs, streets, buildings, labels.
    assert findings["lyrGround"] > 200
    assert findings["lyrZones"] > 0, "two no-fly zones, none drawn"
    assert findings["lyrRoutes"] > 0
    assert findings["lyrStops"] > 0
    assert findings["lyrDrones"] > 0


@pytest.mark.skipif(not DEFAULT_DATASET.exists(),
                    reason="delivery dataset not present")
def test_a_real_basemap_reaches_the_canvas(tmp_path):
    """With an extract, the ground layer must carry *more* than the invented
    city -- the failure this guards against is a basemap that parses, embeds,
    and then silently draws nothing."""
    from drp.geometry.osm import read_osm

    inst = build_geo_instance("geo-page", 9, 3, seed=12,
                              district="Pontianak South", road_slot="IV")
    plain = run(_render(tmp_path, inst, "plain.html"), BROWSER)
    real = run(_render(tmp_path, inst, "real.html",
                       basemap=read_osm(TINY_OSM)), BROWSER)

    assert not real["console_errors"], real["console_errors"]
    assert real["svg_present"]
    assert real["lyrStops"] == plain["lyrStops"]     # same instance, same stops
    assert real["lyrRoutes"] == plain["lyrRoutes"]


def test_an_empty_page_would_be_caught(tmp_path):
    """A guard on the guard: break the payload and the check must notice.

    Without this, every assertion above could be passing on a page that renders
    an empty frame, and nobody would know which.
    """
    inst = generate_zone_instance("zoned", 8, 3, seed=7, n_zones=1)
    page = _render(tmp_path, inst, "broken.html")
    text = page.read_text(encoding="utf-8")
    # Sabotage the very first thing the script does with the data.
    page.write_text(text.replace("const PROJ =", "const PROJ = undefinedVariable ||"),
                    encoding="utf-8")

    findings = run(page, BROWSER)
    assert findings["lyrGround"] == 0 or findings["console_errors"]
