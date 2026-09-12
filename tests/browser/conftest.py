"""Headless-browser harness for the three HTML views (roadmap §2.5).

Everything on those pages is built by JavaScript at load time, so none of it
was reachable from `pytest` before this. Every bug the browser found -- three
temporal-dead-zone crashes, a dead "next improvement" button, a y-axis
squashed to a few pixels, four readouts stuck on "–" at `Home` -- was invisible
in the source and obvious on screen, and every one of them is now a test in
this directory.

How it works, and the three decisions worth knowing about:

**Pages are rendered once per session, from deliberately tiny fixtures.** The
solvers are the slow part, not the browser, so the instances are small and the
budgets are short: the whole session's rendering is a few seconds. The payloads
are handed to the tests alongside the pages, because "the numbers on the page
match the payload that produced them" is only a real assertion if the test
reads the payload rather than a second copy of the expected value.

**GSAP is served from a local cache, not from the CDN.** The pages fetch it
from `cdnjs.cloudflare.com`, which makes a network hiccup look like a test
failure and makes every page load slower than the assertions it feeds. The
first run downloads it to `tests/browser/.cache/`; every run after that -- CI
included, which restores the cache -- serves it from disk through a Playwright
route. If there is no cache and no network, the tests skip with a message
rather than failing or, worse, silently passing against the offline guard.
Fonts are served empty for the same reason.

**Console errors and page errors are collected for every page and asserted
empty.** A page that renders and throws is not a page that works: the
temporal-dead-zone crashes rendered a partial page *and* threw, and would have
passed a smoke test that only looked for elements.

**Pages load with `prefers-reduced-motion: reduce`.** All three honour it by
resolving every transition instantly, so the DOM reaches its final state on the
first frame and an assertion never races an intro tween. `motion_page` opens
one with motion on instead, and asserts it settles in the same place -- which
is the only way the reduced-motion claim in `docs/VISUALISATION.md` is actually
checked.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

sync_api = pytest.importorskip(
    "playwright.sync_api",
    reason="browser tests need playwright: pip install playwright && playwright install chromium",
)

GSAP_URL = "https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"
CACHE_DIR = Path(__file__).parent / ".cache"
GSAP_CACHE = CACHE_DIR / "gsap-3.12.5.min.js"

#: 430 px is the width the three pages are claimed to hold down to, in
#: `PROGRESS.md` §2.2 and in `docs/VISUALISATION.md`. The tests check it.
PHONE_WIDTH = 430
DESKTOP = {"width": 1440, "height": 960}


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "browser: renders a page in a headless browser (needs playwright)")


# ---------------------------------------------------------------------------
# the pages under test
# ---------------------------------------------------------------------------
@dataclass
class RenderedPage:
    """One rendered HTML file and the payload that produced it."""

    path: Path
    data: Dict[str, Any]
    #: Extra context a test may need: the solver result, the instance, ...
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def url(self) -> str:
        return self.path.resolve().as_uri()


@pytest.fixture(scope="session")
def gsap_js() -> str:
    """GSAP's source, from the on-disk cache or, once, from the CDN."""
    if GSAP_CACHE.exists():
        return GSAP_CACHE.read_text(encoding="utf-8")
    try:
        with urllib.request.urlopen(GSAP_URL, timeout=30) as r:
            body = r.read().decode("utf-8")
    except (urllib.error.URLError, OSError) as exc:  # pragma: no cover - network
        pytest.skip(f"GSAP is neither cached at {GSAP_CACHE} nor reachable: {exc}")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    GSAP_CACHE.write_text(body, encoding="utf-8")
    return body


@pytest.fixture(scope="session")
def browser():
    with sync_api.sync_playwright() as pw:
        try:
            b = pw.chromium.launch()
        except Exception as exc:  # pragma: no cover - install state
            pytest.skip(f"no chromium for playwright ({exc}); run "
                        f"`playwright install chromium`")
        yield b
        b.close()


class PageHarness:
    """A loaded page, plus what it said while loading."""

    def __init__(self, page, console: List[str], errors: List[str],
                 rendered: RenderedPage):
        self.page = page
        self.console = console
        self.errors = errors
        self.rendered = rendered

    @property
    def data(self) -> Dict[str, Any]:
        return self.rendered.data

    def assert_clean(self) -> None:
        """No uncaught exception and nothing logged at error level.

        Kept separate from the fixture so a test can deliberately look at a
        page that did misbehave; every test that does not call it explicitly
        gets it from `assert_clean_at_teardown`.
        """
        assert not self.errors, "uncaught page errors:\n  " + "\n  ".join(self.errors)
        assert not self.console, "console errors:\n  " + "\n  ".join(self.console)

    def text(self, selector: str) -> str:
        return (self.page.text_content(selector) or "").strip()

    def numbers(self, selector: str) -> List[float]:
        """Every number in an element's text, in order.

        The pages format numbers for people (`1,214.7`, `56.9%`, `–`), so
        comparing against a payload value means pulling the digits back out.
        """
        raw = self.text(selector).replace(",", "")
        return [float(m) for m in re.findall(r"-?\d+(?:\.\d+)?", raw)]

    def has_horizontal_overflow(self) -> bool:
        return bool(self.page.evaluate(
            "() => document.documentElement.scrollWidth > "
            "document.documentElement.clientWidth + 1"))

    def overflowing_elements(self, limit: int = 6) -> List[str]:
        """Which HTML elements stick out past the viewport, for a useful failure.

        SVG children are skipped deliberately: everything inside a `<svg>` is
        clipped to its viewBox, so a shape whose bounding box runs past the
        right edge is the map working, not the page overflowing. Only the
        elements that can actually push the document wider are reported.
        """
        return self.page.evaluate(
            """(limit) => {
              const w = document.documentElement.clientWidth;
              const out = [];
              for (const el of document.querySelectorAll("body *")) {
                if (el.ownerSVGElement) continue;
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.right > w + 1) {
                  out.push(`${el.tagName.toLowerCase()}.${el.className || "(no class)"}`
                           + ` right=${r.right.toFixed(0)} vw=${w}`);
                  if (out.length >= limit) break;
                }
              }
              return out;
            }""", limit)

    def phone(self) -> None:
        """Resize to phone width and let the layout settle."""
        self.page.set_viewport_size({"width": PHONE_WIDTH, "height": 900})
        self.page.evaluate("() => new Promise(r => requestAnimationFrame(() => "
                           "requestAnimationFrame(r)))")


@pytest.fixture
def open_page(browser, gsap_js):
    """Factory: `open_page(rendered, ready_selector)` -> `PageHarness`.

    `ready_selector` is an element that only exists once the page's script has
    finished building it, so waiting for it is also the assertion that the page
    rendered at all rather than tripping the GSAP guard.
    """
    made = []

    def _open(rendered: RenderedPage, ready: str,
              viewport: Optional[Dict[str, int]] = None,
              timeout: float = 20_000,
              motion: str = "reduce") -> PageHarness:
        ctx = browser.new_context(viewport=viewport or DESKTOP,
                                  device_scale_factor=1,
                                  reduced_motion=motion)
        page = ctx.new_page()
        console: List[str] = []
        errors: List[str] = []
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}")
                if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.route(re.compile(r"cdnjs\.cloudflare\.com/.*gsap.*"),
                   lambda route: route.fulfill(
                       status=200, content_type="application/javascript",
                       body=gsap_js))
        # Fonts are not under test and waiting on them is the slowest part of
        # a load. They are *fulfilled empty* rather than aborted: an aborted
        # request logs a console error, and the whole point of collecting
        # console errors is that the list should be empty. Serving nothing also
        # pins the metrics -- a layout assertion whose result depends on whether
        # Google Fonts answered in time is not a test.
        page.route(re.compile(r"fonts\.googleapis\.com/.*"),
                   lambda route: route.fulfill(status=200,
                                               content_type="text/css", body=""))
        page.route(re.compile(r"fonts\.gstatic\.com/.*"),
                   lambda route: route.fulfill(status=200,
                                               content_type="font/woff2", body=b""))

        page.goto(rendered.url, wait_until="load", timeout=timeout)
        page.wait_for_selector(ready, state="attached", timeout=timeout)
        # One frame, so GSAP's first tick and the initial `render()` have run.
        page.evaluate("() => new Promise(r => requestAnimationFrame(() => "
                      "requestAnimationFrame(r)))")
        made.append(ctx)
        return PageHarness(page, console, errors, rendered)

    yield _open
    for ctx in made:
        ctx.close()


# ---------------------------------------------------------------------------
# fixture pages -- rendered once per session
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def fixture_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("browser-pages")


@pytest.fixture(scope="session")
def flight_page(fixture_dir) -> RenderedPage:
    """The flight replay, on a small zone instance so routes actually detour."""
    from drp.eval.runner import solve_one
    from drp.instances import generate_zone_instance
    from drp.viz.webdata import build_playback_data
    from drp.viz.webplayback import render_playback_html

    inst = generate_zone_instance("browserfix", 16, 8, seed=7, n_zones=3)
    res = solve_one(inst, "alns", seed=1, time_limit=1.5)
    assert res.solution is not None
    # >= 4, not some tighter number: ALNS is time-limited, so how many
    # improving moves land before the clock runs out -- and therefore the
    # final route count -- depends on how fast the machine is, not just the
    # seed. The overlap test below needs several co-located routes to be
    # meaningful; it does not need an exact count.
    assert len([route for route in res.solution.routes if route]) >= 4
    path = fixture_dir / "flight.html"
    render_playback_html(inst, res.solution, path, title="browser fixture")
    data = build_playback_data(inst, res.solution, title="browser fixture")
    return RenderedPage(path, data, {"instance": inst, "solution": res.solution})


@pytest.fixture(scope="session")
def tree_page(fixture_dir) -> RenderedPage:
    """The tree explorer, on an instance B&B finishes so the tree is complete.

    No warm start: the search then has to find its own first solution, which
    is what puts improvements on the scrubber for the "next improvement"
    button to jump between. That button shipped dead, so the test that would
    have caught it needs a page where it has work to do.
    """
    from drp.exact.bnb import solve_bnb
    from drp.instances import generate_zone_instance
    from drp.viz.treedata import build_tree_data
    from drp.viz.webtree import render_tree_html

    inst = generate_zone_instance("browsertree", 6, 3, seed=7, n_zones=1)
    res = solve_bnb(inst, time_limit=10.0, warm_start=None, trace=True,
                    trace_max_nodes=1500)
    path = fixture_dir / "tree.html"
    render_tree_html(inst, res, path, title="browser fixture")
    data = build_tree_data(inst, res, title="browser fixture")
    return RenderedPage(path, data, {"instance": inst, "result": res})


@pytest.fixture(scope="session")
def dash_page(fixture_dir) -> RenderedPage:
    """The convergence dashboard, all three methods plus a reference floor.

    The floor is what pushed the y-range wrong in the bug this file's tests
    pin, so it has to be present in the fixture.
    """
    from drp.exact.bnb import solve_bnb
    from drp.instances import generate_instance
    from drp.meta.alns import solve_alns
    from drp.meta.construct import best_construction
    from drp.meta.ga import solve_ga
    from drp.meta.sa import solve_sa
    from drp.viz.dashdata import MethodRun, build_dashboard_data
    from drp.viz.webdash import render_dashboard_html

    inst = generate_instance("browserdash", 10, 3, seed=5)
    ws = best_construction(inst)
    wt = ws.giant_tour() if ws else None
    common = dict(seed=1, time_limit=1.2, trace=True, trace_max_samples=400)
    ga = solve_ga(inst, warm_tours=[wt] if wt else None, **common)
    sa = solve_sa(inst, warm_tour=wt, **common)
    alns = solve_alns(inst, warm_tour=wt, **common)
    runs = [
        MethodRun("ga", ga.trace, ga.best_energy, ga.time, 1,
                  solution=ga.best_solution, extra={"generations": ga.generations}),
        MethodRun("sa", sa.trace, sa.best_energy, sa.time, 1,
                  solution=sa.best_solution,
                  extra={"iterations": sa.iterations, "accepted": sa.accepted,
                         "accepted_uphill": sa.accepted_uphill,
                         "reheats": sa.reheats}),
        MethodRun("alns", alns.trace, alns.best_energy, alns.time, 1,
                  solution=alns.best_solution,
                  extra={"iterations": alns.iterations,
                         "destroy_weights": alns.destroy_weights,
                         "repair_weights": alns.repair_weights}),
    ]
    ref = solve_bnb(inst, time_limit=4.0, warm_start=ws)
    reference = ref.best_energy if ref.optimal else ref.dual_bound
    label = "B&B optimum" if ref.optimal else "B&B dual bound"

    path = fixture_dir / "dash.html"
    render_dashboard_html(inst, runs, path, reference=reference,
                          reference_label=label, title="browser fixture")
    data = build_dashboard_data(inst, runs, reference=reference,
                                reference_label=label, title="browser fixture")
    return RenderedPage(path, data, {"instance": inst, "bnb": ref})


@pytest.fixture(scope="session")
def planner_server(tmp_path_factory):
    """A live planner server, for the one page that isn't a `file://` URI.

    The other three pages are static files; the planner is a running
    server, so Playwright has to navigate to a real `http://127.0.0.1:PORT/`
    instead. Session-scoped like the other page fixtures -- the server is
    cheap to start, and one solve at a time is exactly what the tests want
    to exercise anyway.
    """
    import threading

    from drp.app.server import make_server

    root = tmp_path_factory.mktemp("planner-server-output")
    srv = make_server(host="127.0.0.1", port=0, output_root=root)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    host, port = srv.server_address[:2]
    yield {"url": f"http://{host}:{port}/", "output_root": root}
    srv.shutdown()
    thread.join(timeout=5)
    srv.server_close()


@pytest.fixture(scope="session")
def payload_of():
    """Read a page's inlined payload back out of the file it was written to.

    Used where a test wants to prove the *file* carries the numbers, not just
    that the builder returned them.
    """
    def _read(rendered: RenderedPage, token: str) -> Dict[str, Any]:
        text = rendered.path.read_text(encoding="utf-8")
        m = re.search(rf"const {token} = (\{{.*?\}});\n", text, re.S)
        assert m, f"no inlined {token} payload in {rendered.path.name}"
        return json.loads(m.group(1).replace("<\\/", "</"))
    return _read
