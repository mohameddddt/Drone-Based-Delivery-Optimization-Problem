"""The B&B search-tree explorer, driven in a headless browser (roadmap §2.5).

`tests/test_viz_tree.py` pins the payload -- the geometry covers every leg it
can be asked to draw, and the derived dual-bound series lands on the solver's
own. This file covers what that cannot: whether the page built from that
payload is the page it claims to be.

Five of the eight bugs §2.4 records were found here by hand. Each has a test
below, named after it.
"""
from __future__ import annotations

import math

import pytest

# `browser` selects them; `slow` keeps them out of `-m "not slow"`, the
# fast subset CI runs on every push, which installs no browser and is
# meant to stay under a couple of minutes.
pytestmark = [pytest.mark.browser, pytest.mark.slow]

READY = "#tree circle"


def _selected_id(h) -> int:
    """The node id the inspector is showing, from `#408 · depth 6`."""
    return int(h.text("#nodeTag").split("·")[0].strip().lstrip("#"))


# ---------------------------------------------------------------------------
# it renders at all
# ---------------------------------------------------------------------------
def test_page_renders_and_the_gsap_guard_did_not_fire(open_page, tree_page):
    h = open_page(tree_page, READY)
    assert h.page.query_selector(".offline-note") is None
    assert h.text("#ttl")
    h.assert_clean()


def test_no_uncaught_errors_anywhere_on_load(open_page, tree_page):
    """The three temporal-dead-zone crashes lived on this page: `readout` and
    `visionStroke` read during camera setup, and `playing` read during the
    first `setT`, each before its own `let`/`const` executed. They threw at
    load and left a partly built page, so counting elements was not enough --
    this is the assertion that would have caught them.
    """
    h = open_page(tree_page, READY)
    h.assert_clean()


def test_one_circle_per_recorded_node(open_page, tree_page):
    h = open_page(tree_page, READY)
    recorded = len(h.data["trace"]["nodes"])
    drawn = h.page.eval_on_selector_all(
        "#tree circle", "els => els.length")
    # One extra circle is the playhead marker in the head layer.
    assert drawn in (recorded, recorded + 1), \
        f"{drawn} circles drawn for {recorded} recorded nodes"
    h.assert_clean()


def test_edges_and_nodes_are_in_separate_layers(open_page, tree_page):
    """§2.4's first bug: every node's incoming edge lived inside that node's
    own `<g>`, so each later edge painted over every earlier circle and the
    tree rendered as a black mass with no nodes in it. Painting order is not
    observable from a screenshot-free test, but the structure that caused it
    is: if any `<g>` under the tree holds both a path and a circle, the layers
    have been merged again.
    """
    h = open_page(tree_page, READY)
    mixed = h.page.evaluate(
        """() => [...document.querySelectorAll("#tree g")]
                 .filter(g => g.querySelector(":scope > path")
                           && g.querySelector(":scope > circle")).length""")
    assert mixed == 0, f"{mixed} group(s) hold edges and nodes together again"
    h.assert_clean()


def test_nodes_are_drawn_with_a_visible_radius(open_page, tree_page):
    """A tree of zero-radius circles satisfies every count above and shows
    nothing."""
    h = open_page(tree_page, READY)
    radii = h.page.eval_on_selector_all(
        "#tree circle", "els => els.map(c => parseFloat(c.getAttribute('r')))")
    assert min(radii) > 0
    h.assert_clean()


def test_the_search_panel_is_populated(open_page, tree_page):
    h = open_page(tree_page, READY)
    kv = h.text("#searchKv")
    assert "Nodes recorded" in kv
    assert "Options considered" in kv
    assert len(h.text("#nodeKv")) > 40
    h.assert_clean()


# ---------------------------------------------------------------------------
# the numbers on the page are the numbers in the payload
# ---------------------------------------------------------------------------
def test_header_reports_the_solvers_own_result(open_page, tree_page):
    h = open_page(tree_page, READY)
    res = h.data["result"]
    assert h.numbers("#sNodes")[0] == res["nodes_explored"]
    assert math.isclose(h.numbers("#sBest")[0], round(res["best_energy"]),
                        abs_tol=1.0)
    assert math.isclose(h.numbers("#sBound")[0], round(res["dual_bound"]),
                        abs_tol=1.0)
    h.assert_clean()


def test_recorded_node_count_matches_the_trace(open_page, tree_page):
    h = open_page(tree_page, READY)
    assert h.numbers("#searchKv")[0] == len(h.data["trace"]["nodes"])
    h.assert_clean()


def test_the_inspector_reports_the_selected_nodes_own_bound(
        open_page, tree_page):
    """Not "a panel opened" -- the panel's numbers must be that node's."""
    h = open_page(tree_page, READY)
    node = {n["id"]: n for n in h.data["trace"]["nodes"]}[_selected_id(h)]
    kv = h.text("#nodeKv")
    assert f"{node['lower_bound']:.1f}" in kv
    if node["incumbent"] is not None:
        assert f"{node['incumbent']:.1f}" in kv
    h.assert_clean()


def test_clicking_a_node_moves_the_inspector_to_that_node(
        open_page, tree_page):
    h = open_page(tree_page, READY)
    before = _selected_id(h)
    # Pick a node that is not the one already selected.
    target = h.page.evaluate(
        """(before) => {
             const c = [...document.querySelectorAll("#tree circle")]
               .find(el => el.dataset.i !== undefined
                        && Number(el.dataset.i) !== before);
             return c ? Number(c.dataset.i) : null;
           }""", before)
    assert target is not None
    h.page.evaluate(
        """(i) => document.querySelector(`#tree circle[data-i="${i}"]`)
                    .dispatchEvent(new MouseEvent("click", {bubbles: true}))""",
        target)
    h.page.wait_for_timeout(250)
    after = _selected_id(h)
    assert after != before
    assert after == h.data["trace"]["nodes"][target]["id"]
    h.assert_clean()


# ---------------------------------------------------------------------------
# the controls do what they claim
# ---------------------------------------------------------------------------
def test_the_page_opens_on_the_node_that_produced_the_answer(
        open_page, tree_page):
    """§2.4's third bug had two halves. This is the second: the page used to
    open on the root while the playhead sat at the end of the search, so the
    inspector contradicted the scrubber."""
    h = open_page(tree_page, READY)
    nodes = h.data["trace"]["nodes"]
    incumbents = [n for n in nodes if n["status"] == "new_incumbent"]
    if not incumbents:
        pytest.skip("this fixture's search found no incumbent")
    assert _selected_id(h) == incumbents[-1]["id"]
    assert h.numbers("#rdNode")[0] == len(nodes) - 1, \
        "the playhead should open at the end of the search"
    h.assert_clean()


def test_next_improvement_wraps_instead_of_doing_nothing(
        open_page, tree_page):
    """§2.4's third bug, first half: "next improvement" was dead on arrival,
    because the page opens with the playhead at the *end* of the search, where
    there is no next improvement. It wraps now. A test that only asserted the
    button exists would have passed the whole time it was broken.
    """
    h = open_page(tree_page, READY)
    improvements = [n for n in h.data["trace"]["nodes"]
                    if n["status"] == "new_incumbent"]
    if len(improvements) < 2:
        pytest.skip("needs at least two improvements to jump between")
    assert not h.page.is_disabled("#nextImp")
    before = _selected_id(h)
    h.page.click("#nextImp")
    h.page.wait_for_timeout(250)
    after = _selected_id(h)
    assert after != before, "next improvement did nothing at the end of the search"
    assert after == improvements[0]["id"], "it should have wrapped to the first"
    h.assert_clean()


def test_previous_improvement_wraps_back(open_page, tree_page):
    h = open_page(tree_page, READY)
    improvements = [n for n in h.data["trace"]["nodes"]
                    if n["status"] == "new_incumbent"]
    if len(improvements) < 2:
        pytest.skip("needs at least two improvements to jump between")
    h.page.click("#nextImp")
    h.page.wait_for_timeout(200)
    h.page.click("#prevImp")
    h.page.wait_for_timeout(200)
    assert _selected_id(h) == improvements[-1]["id"]
    h.assert_clean()


def test_every_improvement_is_reachable_by_walking_forwards(
        open_page, tree_page):
    """Stronger than "the button moves": walking it `len(improvements)` times
    must visit every improvement and come back to where it started."""
    h = open_page(tree_page, READY)
    improvements = [n["id"] for n in h.data["trace"]["nodes"]
                    if n["status"] == "new_incumbent"]
    if len(improvements) < 2:
        pytest.skip("needs at least two improvements to jump between")
    seen = []
    for _ in range(len(improvements)):
        h.page.click("#nextImp")
        h.page.wait_for_timeout(120)
        seen.append(_selected_id(h))
    assert sorted(seen) == sorted(improvements)
    h.assert_clean()


def test_the_scrubber_seeks_and_hides_later_nodes(open_page, tree_page):
    """Seeking back through expansion order must actually remove nodes from the
    drawing -- "nodes appear and disappear in expansion order"."""
    h = open_page(tree_page, READY)
    visible = """() => [...document.querySelectorAll("#tree circle")]
                       .filter(c => c.getAttribute("opacity") !== "0"
                                 && getComputedStyle(c).display !== "none"
                                 && c.style.visibility !== "hidden").length"""
    at_end = h.page.evaluate(visible)
    el = h.page.query_selector("#scrub")
    el.scroll_into_view_if_needed()
    h.page.wait_for_timeout(60)
    box = el.bounding_box()
    y = box["y"] + box["height"] / 2
    h.page.mouse.move(box["x"] + box["width"] * 0.5, y)
    h.page.mouse.down()
    h.page.mouse.move(box["x"] + 1, y)
    h.page.mouse.up()
    h.page.wait_for_timeout(250)
    assert h.numbers("#rdNode")[0] < len(h.data["trace"]["nodes"]) - 1
    assert h.page.evaluate(visible) < at_end
    h.assert_clean()


def test_play_advances_the_search_replay(open_page, tree_page):
    h = open_page(tree_page, READY)
    h.page.focus("#scrub")
    h.page.keyboard.press("Home")
    h.page.wait_for_timeout(150)
    start = h.numbers("#rdNode")[0]
    h.page.click("#playBtn")
    h.page.wait_for_function(
        """(start) => parseFloat(document.getElementById("rdNode").textContent
             .replace(/,/g, "")) > start""", arg=start, timeout=6000)
    h.page.click("#playBtn")
    h.assert_clean()


def test_keyboard_seeks_on_the_scrubber(open_page, tree_page):
    h = open_page(tree_page, READY)
    h.page.focus("#scrub")
    h.page.keyboard.press("Home")
    h.page.wait_for_timeout(150)
    assert h.numbers("#rdNode")[0] == 0
    h.page.keyboard.press("End")
    h.page.wait_for_timeout(150)
    assert h.numbers("#rdNode")[0] == len(h.data["trace"]["nodes"]) - 1
    h.assert_clean()


# ---------------------------------------------------------------------------
# the colour encoding
# ---------------------------------------------------------------------------
def test_the_ramp_legend_prints_both_ends_as_numbers(open_page, tree_page):
    """§2.4's fifth bug: on a run that never found a feasible solution the ramp
    root-bound-to-incumbent had zero span and every node came out one colour --
    in exactly the run where the bound is the only thing to look at. The legend
    now prints both ends and says which it is showing, so a collapsed ramp is
    visible in the text rather than only in the picture.
    """
    h = open_page(tree_page, READY)
    label = h.text("#rampLabel")
    assert "(root)" in label
    assert "incumbent" in label or "deepest" in label
    numbers = h.numbers("#rampLabel")
    assert len(numbers) >= 2
    assert numbers[1] > numbers[0], "the ramp must span a positive range"
    h.assert_clean()


def test_the_ramp_comes_from_the_payloads_theme(open_page, tree_page):
    """The ramp *is* the encoding on this page, so a legend painted from a
    different set of stops than the nodes would be worse than no legend."""
    h = open_page(tree_page, READY)
    stops = h.data["theme"]["ramp"]
    css = h.page.evaluate(
        """() => getComputedStyle(document.querySelector(".ramp .bar"))
                   .backgroundImage""")
    for hexcode in stops:
        r, g, b = (int(hexcode[i:i + 2], 16) for i in (1, 3, 5))
        assert f"rgb({r}, {g}, {b})" in css, f"{hexcode} missing from the legend ramp"
    h.assert_clean()


def test_node_rings_carry_a_dash_pattern_per_status(open_page, tree_page):
    """The second channel (roadmap §2.5). It matters more here than anywhere
    else on the page, because the fill under the ring is itself a colour from
    the bound ramp."""
    h = open_page(tree_page, READY)
    dashes = h.page.evaluate(
        """() => {
             const out = {};
             for (const c of document.querySelectorAll("#tree circle")) {
               if (c.dataset.i === undefined) continue;
               out[c.dataset.i] = c.getAttribute("stroke-dasharray");
             }
             return out;
           }""")
    expected = h.data["theme"]["status_dashes"]
    nodes = h.data["trace"]["nodes"]
    checked = 0
    for i_str, dash in dashes.items():
        status = nodes[int(i_str)]["status"]
        if status not in expected or not expected[status]:
            continue
        assert dash == expected[status], \
            f"node {i_str} ({status}) drew dash {dash!r}, expected {expected[status]!r}"
        checked += 1
    assert checked > 0, "no node carried a status dash at all"
    h.assert_clean()


# ---------------------------------------------------------------------------
# layout
# ---------------------------------------------------------------------------
def test_no_horizontal_overflow_at_430px(open_page, tree_page):
    h = open_page(tree_page, READY)
    h.phone()
    assert not h.has_horizontal_overflow(), \
        "page scrolls sideways at 430px: " + "; ".join(h.overflowing_elements())
    h.assert_clean()


def test_the_mini_map_is_not_hidden_behind_a_scrollbar(open_page, tree_page):
    """§2.4's fourth bug: the rail was height-bound to the tree, which put the
    mini map behind an inner scrollbar. The tree panel stretches to the row
    instead -- safe here, unlike §2.2's bug, because the rail's height does not
    feed back into the tree panel's width."""
    h = open_page(tree_page, READY)
    hidden = h.page.evaluate(
        """() => {
             const rail = document.querySelector(".rail");
             return {maxH: rail.style.maxHeight,
                     clipped: rail.scrollHeight > rail.clientHeight + 1};
           }""")
    assert hidden["maxH"] == "", "the rail is height-bound again"
    assert not hidden["clipped"], "the rail is scrolling internally again"
    assert h.page.query_selector("#mini") is not None
    h.assert_clean()
