"""The B&B tree explorer and Solver Vision payloads (roadmap §2.4, steps 3-4).

`tests/test_bnb_trace.py` proves the trace is a faithful record of the search.
These tests prove the two payloads built on top of it stay faithful:

- the explorer's geometry covers everything it can be asked to draw, and its
  numbers are the solver's own;
- the one *derived* series on the page -- the dual bound closing on the
  incumbent -- is derived by the solver's own rule, checked by reproducing it
  here and landing on `BnBResult.dual_bound` exactly;
- Solver Vision never shows an option the search did not consider, and says so
  when the search has nothing to say about a route.

As with `test_viz_web.py`, this is the Python side. The JavaScript is covered by
driving the rendered pages in a browser, not by CI.
"""
from __future__ import annotations

import heapq
import json
import math

import pytest

from drp.exact.bnb import solve_bnb
from drp.eval.runner import solve_one
from drp.instances import generate_instance, generate_zone_instance
from drp.meta.construct import best_construction
from drp.viz.treedata import build_tree_data, build_vision_data, leg_paths
from drp.viz.webplayback import (DATA_TOKEN, VISION_TOKEN,
                                 render_playback_html)
from drp.viz.webtree import DATA_TOKEN as TREE_DATA_TOKEN
from drp.viz.webtree import NAME_TOKEN as TREE_NAME_TOKEN
from drp.viz.webtree import render_tree_html


def _traced(inst, time_limit=60.0, max_nodes=10 ** 9, warm=True):
    return solve_bnb(inst, time_limit=time_limit,
                     warm_start=best_construction(inst) if warm else None,
                     trace=True, trace_max_nodes=max_nodes)


# ---------------------------------------------------------------------------
# the explorer payload
# ---------------------------------------------------------------------------
def test_build_tree_data_refuses_an_untraced_result():
    inst = generate_instance("notrace", 6, 2, seed=5)
    res = solve_bnb(inst, time_limit=10.0)
    with pytest.raises(ValueError, match="trace"):
        build_tree_data(inst, res)


def test_tree_data_carries_the_whole_trace_and_the_solver_s_own_numbers():
    inst = generate_instance("tree", 7, 3, seed=301)
    res = _traced(inst)
    d = build_tree_data(inst, res)

    assert len(d["trace"]["nodes"]) == len(res.trace.nodes) == res.nodes_explored
    assert d["result"]["nodes_explored"] == res.nodes_explored
    assert d["result"]["best_energy"] == pytest.approx(res.best_energy)
    assert d["result"]["dual_bound"] == pytest.approx(res.dual_bound)
    assert d["result"]["optimal"] is res.optimal
    assert d["result"]["summary"] == res.summary()
    assert d["solution"]["routes"], "the optimum should be attached"


def test_tree_data_has_a_path_for_every_leg_the_page_can_draw():
    """The explorer assembles partial routes and ghost legs out of `paths`; a
    missing entry would silently become a straight line through a no-fly zone."""
    inst = generate_zone_instance("ztree", 8, 3, seed=2026, n_zones=2)
    res = _traced(inst, max_nodes=1500)
    d = build_tree_data(inst, res)
    paths = d["paths"]

    def key(a, b):
        return f"{min(a, b)}-{max(a, b)}"

    for n in res.trace.nodes:
        for r in n.closed_routes:
            chain = [0] + list(r) + [0]
            for a, b in zip(chain[:-1], chain[1:]):
                assert key(a, b) in paths, f"closed leg {a}-{b} has no path"
        chain = [0] + list(n.open_route)
        for a, b in zip(chain[:-1], chain[1:]):
            assert key(a, b) in paths, f"open leg {a}-{b} has no path"
        tip = n.open_route[-1] if n.open_route else 0
        for c in n.candidates:
            a = tip if c.kind == "extend" else 0
            assert key(a, c.customer) in paths, "candidate leg has no path"

    for pts in paths.values():
        assert len(pts) >= 2
        assert all(len(p) == 2 for p in pts)


def test_tree_data_leg_paths_detour_around_zones():
    """Same claim `test_viz_web.py` makes for the replay: the explorer's map has
    to fly what the solution flies."""
    inst = generate_zone_instance("zdetour", 10, 3, seed=2026, n_zones=4)
    paths = leg_paths(inst, [(i, j) for i in range(inst.N)
                             for j in range(i + 1, inst.N)])
    bent = {k: pts for k, pts in paths.items() if len(pts) > 2}
    assert bent, "no leg detoured; pick an instance where the geometry bites"

    co = inst.coords
    for key, pts in paths.items():
        a, b = (int(x) for x in key.split("-"))
        assert pts[0] == pytest.approx(list(co[a]))
        assert pts[-1] == pytest.approx(list(co[b]))
        flown = sum(math.dist(p, q) for p, q in zip(pts[:-1], pts[1:]))
        direct = math.dist(co[a], co[b])
        assert flown >= direct - 1e-6
        if key in bent:
            assert flown > direct + 1e-6, "a bent leg must be longer than the hop"
        # and the detour is what the distance matrix charges for
        assert flown == pytest.approx(inst.dist[a, b], rel=1e-9)


def test_tree_data_is_json_safe():
    inst = generate_instance("jsontree", 7, 3, seed=302)
    res = _traced(inst)
    text = json.dumps(build_tree_data(inst, res), allow_nan=False)
    assert "Infinity" not in text and "NaN" not in text


def test_render_tree_html_substitutes_both_placeholders(tmp_path):
    inst = generate_instance("plaintree", 6, 2, seed=303)
    res = _traced(inst)
    out = render_tree_html(inst, res, tmp_path / "sub" / "tree.html")

    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert TREE_DATA_TOKEN not in text
    assert TREE_NAME_TOKEN not in text
    assert "<script" in text
    assert '"name": "plaintree"' in text
    assert out.stat().st_size > 20_000


# ---------------------------------------------------------------------------
# the one derived series on the page
# ---------------------------------------------------------------------------
def _dual_bound_series(trace):
    """The rule `tree_template.html` uses, reimplemented here.

    After processing node `t` the open frontier is every explored-candidate
    child of nodes 0..t whose own id exceeds `t`, plus -- once the clock has
    stopped -- the node it stopped at and every sibling generated but never
    entered. That is exactly the frontier `solve_bnb` minimises over, so the
    last value of this series must be the dual bound it reports.
    """
    nodes = trace.nodes
    idx = {n.id: i for i, n in enumerate(nodes)}
    first_timeout = next((i for i, n in enumerate(nodes)
                          if n.status == "timeout"), None)
    stranded = [c.bound for n in nodes for c in n.candidates
                if c.outcome == "unexplored" and c.bound is not None]

    heap, done, out = [], set(), []
    ub = math.inf
    for t, n in enumerate(nodes):
        if n.status != "timeout":
            done.add(t)
        if n.incumbent is not None and math.isfinite(n.incumbent):
            ub = min(ub, n.incumbent)
        if n.status == "new_incumbent" and n.committed is not None:
            ub = min(ub, n.committed)
        for c in n.candidates:
            if c.outcome == "explored" and c.child is not None and c.bound is not None:
                ci = idx.get(c.child)
                if ci is not None:
                    heapq.heappush(heap, (c.bound, ci))
        if t == first_timeout:
            for b in stranded:
                heapq.heappush(heap, (b, -1))
        while heap and heap[0][1] >= 0 and heap[0][1] in done:
            heapq.heappop(heap)
        lb = heap[0][0] if heap else (ub if math.isfinite(ub) else trace.root_bound)
        out.append(min(lb, ub) if math.isfinite(ub) else lb)
    return out


@pytest.mark.parametrize("seed,n,k", [(1, 7, 3), (2, 8, 3), (3, 8, 2)])
def test_derived_dual_bound_lands_on_the_solver_s_own(seed, n, k):
    """The page draws the bound closing on the incumbent. If that curve did not
    finish where `solve_bnb` says the bound finished, it would be a plausible
    picture of a search that never happened."""
    inst = generate_instance(f"ser{seed}", n, k, 300 + seed)
    res = _traced(inst)
    series = _dual_bound_series(res.trace)

    assert len(series) == res.nodes_explored
    assert series[-1] == pytest.approx(res.dual_bound, abs=1e-6)
    # a lower bound never exceeds the optimum, at any point along the way
    for v in series:
        assert v <= res.best_energy + 1e-6


def test_derived_dual_bound_lands_on_the_solver_s_own_after_a_timeout():
    inst = generate_instance("serto", 12, 4, 11)
    res = _traced(inst, time_limit=0.25)
    if not res.timed_out:
        pytest.skip("instance finished inside the limit")
    series = _dual_bound_series(res.trace)
    assert series[-1] == pytest.approx(res.dual_bound, abs=1e-6)


# ---------------------------------------------------------------------------
# Solver Vision
# ---------------------------------------------------------------------------
def test_vision_refuses_an_untraced_result():
    inst = generate_instance("nov", 6, 2, seed=7)
    res = solve_bnb(inst, time_limit=10.0)
    assert res.best_solution is not None
    with pytest.raises(ValueError, match="trace"):
        build_vision_data(inst, res.best_solution, res)


def test_vision_matches_every_step_of_the_search_s_own_solution():
    """Replaying B&B's own optimum against B&B's own trace, every step of every
    route must find the node where the search stood exactly there."""
    inst = generate_instance("vis", 7, 3, seed=301)
    res = _traced(inst)
    v = build_vision_data(inst, res.best_solution, res)

    assert v["total"] == sum(len(r) for r in res.best_solution.routes if r)
    assert v["matched"] == v["total"]
    assert v["exact"] == v["total"], \
        "the search's own solution must match on full state, not just prefix"
    assert v["optimal"] is True


def test_vision_never_reports_an_option_that_was_taken():
    inst = generate_instance("vis2", 8, 3, seed=302)
    res = _traced(inst)
    v = build_vision_data(inst, res.best_solution, res)

    seen = 0
    for st in v["steps"]:
        for r in st["rejected"]:
            seen += 1
            assert r["outcome"] != "explored"
            # the customer rejected here is never the one the route went on to
            assert not (r["customer"] == st["customer"] and r["from"] == st["from"])
    assert seen > 0, "nothing was rejected; this test proved nothing"


def test_vision_has_a_path_for_every_ghost_leg_it_asks_the_page_to_draw():
    inst = generate_zone_instance("visz", 8, 3, seed=2026, n_zones=2)
    res = _traced(inst)
    v = build_vision_data(inst, res.best_solution, res)
    for st in v["steps"]:
        for r in st["rejected"]:
            a, b = r["from"], r["customer"]
            assert f"{min(a, b)}-{max(a, b)}" in v["paths"]


def test_vision_against_a_solution_the_search_did_not_produce():
    """A replay of an ALNS solution against a B&B trace is legitimate. Where the
    search never stood at a point in that route there must simply be no entry --
    never a fabricated one -- and the shortfall must be reported."""
    inst = generate_instance("visx", 10, 3, seed=404)
    alns = solve_one(inst, "alns", seed=1, time_limit=2.0)
    assert alns.solution is not None
    res = _traced(inst, time_limit=2.0, max_nodes=3000)

    v = build_vision_data(inst, alns.solution, res)
    assert v["total"] == sum(len(r) for r in alns.solution.routes if r)
    assert v["matched"] <= v["total"]
    assert v["exact"] <= v["matched"]
    assert len(v["steps"]) == v["matched"]
    # every step names a node that really is in the trace
    ids = {n.id for n in res.trace.nodes}
    for st in v["steps"]:
        assert st["node"] in ids


def test_vision_step_state_agrees_with_the_node_it_names():
    """A step claims the search stood at this point in this route. Check it: the
    named node's open route must end at the customer the step is about."""
    inst = generate_instance("visstate", 8, 3, seed=305)
    res = _traced(inst)
    byid = {n.id: n for n in res.trace.nodes}
    v = build_vision_data(inst, res.best_solution, res)
    for st in v["steps"]:
        n = byid[st["node"]]
        assert n.open_route[-1] == st["customer"]
        assert len(n.open_route) == st["index"] + 1
        if st["index"] > 0:
            assert n.open_route[-2] == st["from"]
        else:
            assert st["from"] == 0


def test_render_playback_html_embeds_vision_only_when_given_one(tmp_path):
    inst = generate_instance("visren", 7, 3, seed=301)
    res = _traced(inst)

    plain = render_playback_html(inst, res.best_solution, tmp_path / "plain.html")
    text = plain.read_text(encoding="utf-8")
    assert VISION_TOKEN not in text
    assert "const VISION = null" in text
    assert DATA_TOKEN not in text

    v = build_vision_data(inst, res.best_solution, res)
    withv = render_playback_html(inst, res.best_solution, tmp_path / "v.html",
                                 vision=v)
    text = withv.read_text(encoding="utf-8")
    assert VISION_TOKEN not in text
    assert "const VISION = null" not in text
    assert '"steps"' in text
    assert withv.stat().st_size > plain.stat().st_size
