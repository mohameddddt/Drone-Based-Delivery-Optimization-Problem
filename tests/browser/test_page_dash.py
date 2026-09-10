"""The convergence dashboard, driven in a headless browser (roadmap §2.5).

`tests/test_viz_dash.py` pins the payload -- the shared axis limits contain
every series, the three numbers that must agree do, and no method reports an
energy below a proven optimum. All three of the bugs §2.4 found on this page
were about the *vertical axis*, which is a property of the drawing and not of
the payload, so none of them were reachable from Python.
"""
from __future__ import annotations

import math

import pytest

# `browser` selects them; `slow` keeps them out of `-m "not slow"`, the
# fast subset CI runs on every push, which installs no browser and is
# meant to stay under a couple of minutes.
pytestmark = [pytest.mark.browser, pytest.mark.slow]

READY = "#legendMain span"


def _best_curve_span(h):
    """How much of the plot height the best-so-far curves actually occupy.

    The three curves are the only paths drawn at stroke-width 2.1 -- working
    solutions are 1, the reference is 1.4 -- so this measures exactly the thing
    the chart exists to show.
    """
    return h.page.evaluate(
        """() => {
             const paths = [...document.querySelectorAll("#chartMain path")]
                 .filter(p => p.getAttribute("stroke-width") === "2.1");
             const plot = document.getElementById("chartMain")
                 .getBoundingClientRect();
             let lo = Infinity, hi = -Infinity;
             for (const p of paths){
               const r = p.getBoundingClientRect();
               lo = Math.min(lo, r.top); hi = Math.max(hi, r.bottom);
             }
             return {curves: paths.length, span: hi - lo, plot: plot.height,
                     frac: (hi - lo) / plot.height};
           }""")


def _click_toggle(h, label):
    h.page.get_by_role("button", name=label, exact=True).click()
    h.page.wait_for_timeout(250)


# ---------------------------------------------------------------------------
# it renders at all
# ---------------------------------------------------------------------------
def test_page_renders_and_the_gsap_guard_did_not_fire(open_page, dash_page):
    h = open_page(dash_page, READY)
    assert h.page.query_selector(".offline-note") is None
    assert h.text("#ttl")
    h.assert_clean()


def test_no_uncaught_errors_anywhere_on_load(open_page, dash_page):
    h = open_page(dash_page, READY)
    h.assert_clean()


def test_one_panel_and_one_legend_pair_per_method(open_page, dash_page):
    h = open_page(dash_page, READY)
    methods = h.data["methods"]
    legend = h.text("#legendMain")
    for m in methods:
        assert f"{m['label']} best" in legend
        assert f"{m['label']} working" in legend
    assert h.page.eval_on_selector_all(
        "#panels > *", "els => els.length") == len(methods)
    h.assert_clean()


def test_every_method_draws_a_best_so_far_curve(open_page, dash_page):
    h = open_page(dash_page, READY)
    got = _best_curve_span(h)
    assert got["curves"] == len(h.data["methods"])
    h.assert_clean()


def test_panels_are_populated_not_empty_shells(open_page, dash_page):
    h = open_page(dash_page, READY)
    text = h.text("#panels")
    assert "Best so far" in text
    assert "Working solution" in text
    assert h.text("#caveat"), "the one-run-per-method caveat must be on the page"
    h.assert_clean()


# ---------------------------------------------------------------------------
# the vertical axis -- where a multi-method chart goes wrong
# ---------------------------------------------------------------------------
def test_fit_best_does_not_squash_the_curves_into_a_band(open_page, dash_page):
    """§2.4's sixth bug, and the one this whole view exists to avoid. The
    y-range used to contain SA's working solution, which wanders far above
    every best-so-far curve, so the three curves the chart is *for* occupied a
    few pixels at the bottom. Measured on the fixture as it stands: `fit best`
    gives the curves ~79% of the plot height and `fit all` ~2%. Anything under
    a quarter is the bug back.
    """
    h = open_page(dash_page, READY)
    got = _best_curve_span(h)
    assert got["frac"] > 0.25, (
        f"best-so-far curves occupy only {got['frac']:.1%} of the plot "
        f"({got['span']:.0f}px of {got['plot']:.0f}px)")
    h.assert_clean()


def test_fit_all_widens_the_range_and_fit_best_restores_it(
        open_page, dash_page):
    """The toggle has to actually change the drawing, in the direction claimed:
    `fit all` includes the working solutions and the floor, so the best-so-far
    curves must get *less* of the plot, not more."""
    h = open_page(dash_page, READY)
    fit_best = _best_curve_span(h)["frac"]
    _click_toggle(h, "fit all")
    fit_all = _best_curve_span(h)["frac"]
    assert fit_all < fit_best, \
        f"'fit all' did not widen the range ({fit_all:.1%} vs {fit_best:.1%})"
    _click_toggle(h, "fit best")
    assert math.isclose(_best_curve_span(h)["frac"], fit_best, abs_tol=0.02)
    h.assert_clean()


def test_the_page_names_the_curves_it_clipped(open_page, dash_page):
    """"The page tells you which curves it has clipped rather than letting the
    legend promise a line you cannot find." If nothing is clipped the note is
    empty, which is also correct -- so this asserts the note is *consistent*
    with the mode rather than merely present."""
    h = open_page(dash_page, READY)
    clipped = h.text("#clipNote")
    if clipped:
        assert "working solution" in clipped
        assert any(m["label"] in clipped for m in h.data["methods"])
    _click_toggle(h, "fit all")
    assert h.text("#clipNote") == "", \
        "'fit all' clips nothing, so it must not claim to"
    h.assert_clean()


def test_the_reference_floor_is_labelled_for_what_it_is(open_page, dash_page):
    """An unproven incumbent is not a floor. The page must say which of the two
    it is drawing, because they mean different things."""
    h = open_page(dash_page, READY)
    label = h.data["reference_label"]
    assert label in ("B&B optimum", "B&B dual bound")
    assert label in h.text("#legendMain")
    h.assert_clean()


# ---------------------------------------------------------------------------
# the readouts
# ---------------------------------------------------------------------------
def test_home_does_not_leave_every_readout_empty(open_page, dash_page):
    """§2.4's eighth bug: the x-domain began at 0 but the first sample lands a
    few milliseconds in, so pressing `Home` landed in a sliver where no method
    had produced a sample and every readout said "–". The domain starts at the
    first real sample now, so at `Home` at least one method reports a number.

    Not "all of them": the domain starts at the *earliest* first sample across
    methods, and a method that has not sampled yet at that instant genuinely
    has nothing to report. Asserting otherwise would be asking the page to
    invent a value.
    """
    h = open_page(dash_page, READY)
    h.page.focus("#scrub")
    h.page.keyboard.press("Home")
    h.page.wait_for_timeout(200)
    assert h.text("#rdX") != "–"
    assert h.numbers("#rdX"), f"x readout says {h.text('#rdX')!r} at Home"
    bests = h.text("#rdBests")
    assert h.numbers("#rdBests"), f"no method reported a value at Home: {bests!r}"
    h.assert_clean()


def test_end_reports_every_methods_final_best(open_page, dash_page):
    """At the end of the run every method has finished, so every readout must
    carry a number -- and it must be that method's own best energy."""
    h = open_page(dash_page, READY)
    h.page.focus("#scrub")
    h.page.keyboard.press("End")
    h.page.wait_for_timeout(250)
    shown = h.numbers("#rdBests")
    assert "–" not in h.text("#rdBests")
    for m in h.data["methods"]:
        assert any(math.isclose(v, round(m["best_energy"]), abs_tol=1.0)
                   for v in shown), \
            f"{m['label']}'s best {m['best_energy']:.1f} is not in {shown}"
    h.assert_clean()


def test_the_header_reports_each_methods_best_energy(open_page, dash_page):
    h = open_page(dash_page, READY)
    shown = h.numbers("#winners")
    for m in h.data["methods"]:
        assert any(math.isclose(v, round(m["best_energy"]), abs_tol=1.0)
                   for v in shown), \
            f"{m['label']}'s best {m['best_energy']:.1f} is not in the header {shown}"
    h.assert_clean()


# ---------------------------------------------------------------------------
# the controls do what they claim
# ---------------------------------------------------------------------------
def test_the_step_axis_is_labelled_not_comparable(open_page, dash_page):
    """One GA generation evaluates `pop_size` tours; one SA iteration evaluates
    one. Putting them on a shared step axis silently claims those cost the
    same, so selecting it has to say so."""
    h = open_page(dash_page, READY)
    assert "second" in h.text("#axisNote")
    _click_toggle(h, "steps")
    note = h.text("#axisNote")
    assert "not comparable across methods" in note
    _click_toggle(h, "seconds")
    assert "second" in h.text("#axisNote")
    h.assert_clean()


def test_switching_the_axis_redraws_the_chart(open_page, dash_page):
    """The label changing is not evidence the chart did."""
    h = open_page(dash_page, READY)
    seconds_end = h.text("#axEnd")
    _click_toggle(h, "steps")
    steps_end = h.text("#axEnd")
    assert steps_end != seconds_end
    assert h.numbers("#axEnd")[0] == pytest.approx(
        h.data["meta"]["step_max"], rel=0.02)
    h.assert_clean()


def test_play_advances_the_run(open_page, dash_page):
    h = open_page(dash_page, READY)
    h.page.focus("#scrub")
    h.page.keyboard.press("Home")
    h.page.wait_for_timeout(150)
    start = h.numbers("#rdX")[0]
    h.page.click("#playBtn")
    h.page.wait_for_function(
        """(start) => parseFloat(document.getElementById("rdX").textContent) > start""",
        arg=start, timeout=6000)
    h.page.click("#playBtn")
    h.assert_clean()


def test_the_scrubber_moves_one_playhead_across_every_panel(
        open_page, dash_page):
    """"A scrubber that moves one playhead across every panel at once" -- so
    seeking must move the head in the main chart and in each method's panel,
    not only in the one that was clicked."""
    h = open_page(dash_page, READY)
    heads = """() => [...document.querySelectorAll("line")]
                 .filter(l => l.getAttribute("stroke-dasharray") === "3 3")
                 .map(l => l.getAttribute("x1"))"""
    h.page.focus("#scrub")
    h.page.keyboard.press("Home")
    h.page.wait_for_timeout(200)
    at_home = h.page.evaluate(heads)
    h.page.keyboard.press("End")
    h.page.wait_for_timeout(200)
    at_end = h.page.evaluate(heads)
    assert at_home and len(at_home) == len(at_end)
    assert at_home != at_end, "no playhead moved between Home and End"
    moved = sum(1 for a, b in zip(at_home, at_end) if a != b)
    assert moved == len(at_home), \
        f"only {moved} of {len(at_home)} playheads moved"
    h.assert_clean()


# ---------------------------------------------------------------------------
# the theme reaches the page
# ---------------------------------------------------------------------------
def test_each_method_curve_uses_the_payloads_colour_and_dash(
        open_page, dash_page):
    """Three curves crossing in one chart stay three curves without relying on
    hue -- the second channel (roadmap §2.5). Two methods sharing a dash
    pattern would put the whole weight back on colour."""
    h = open_page(dash_page, READY)
    drawn = h.page.evaluate(
        """() => [...document.querySelectorAll("#chartMain path")]
             .filter(p => p.getAttribute("stroke-width") === "2.1")
             .map(p => ({stroke: p.getAttribute("stroke"),
                         dash: p.getAttribute("stroke-dasharray")}))""")
    expected = [{"stroke": m["color"], "dash": m["dash"]}
                for m in h.data["methods"]]
    assert drawn == expected
    dashes = [d["dash"] for d in drawn]
    assert len(set(dashes)) == len(dashes), f"two methods share a dash: {dashes}"
    h.assert_clean()


def test_the_legend_rule_carries_the_same_dash_as_the_curve(
        open_page, dash_page):
    """A legend showing a solid rule for a dashed curve defeats the point of
    having a dash at all."""
    h = open_page(dash_page, READY)
    rules = h.page.evaluate(
        """() => [...document.querySelectorAll("#legendMain svg line")]
             .map(l => l.getAttribute("stroke-dasharray"))""")
    for m in h.data["methods"]:
        assert rules.count(m["dash"]) >= 2, \
            f"{m['label']}'s dash {m['dash']!r} is missing from the legend rules"
    h.assert_clean()


# ---------------------------------------------------------------------------
# layout
# ---------------------------------------------------------------------------
def test_no_horizontal_overflow_at_430px(open_page, dash_page):
    h = open_page(dash_page, READY)
    h.phone()
    assert not h.has_horizontal_overflow(), \
        "page scrolls sideways at 430px: " + "; ".join(h.overflowing_elements())
    h.assert_clean()


def test_it_reflows_to_one_column_on_a_phone(open_page, dash_page):
    """`docs/VISUALISATION.md` claims this; nothing checked it."""
    h = open_page(dash_page, READY)
    h.phone()
    lefts = h.page.eval_on_selector_all(
        "#panels > *", "els => els.map(e => Math.round(e.getBoundingClientRect().x))")
    assert len(set(lefts)) == 1, f"panels are still side by side at 430px: {lefts}"
    h.assert_clean()
