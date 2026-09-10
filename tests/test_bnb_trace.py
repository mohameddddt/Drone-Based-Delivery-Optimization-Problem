"""The B&B search trace (roadmap §2.4), against the search it claims to record.

The trace exists to be *drawn* -- the tree explorer sizes and colours nodes by
their bound, and Solver Vision in the flight replay draws the partial routes a
node rejected. That makes it exactly the kind of artefact that can look
plausible and be wrong, so these tests treat it as a claim about the search
rather than as a data structure to smoke-test:

1. It is complete: one record per node the search actually entered.
2. It is connected: every parent id exists, and every candidate that says it
   became a child names a node whose parent is the node that said it.
3. Its bounds behave like bounds: non-decreasing down the tree, and a pruned
   node's bound really does dominate the incumbent it was compared against.
4. It is free: with tracing on, the solver returns the identical solution,
   energy, node count and dual bound it returns with tracing off.

(3) is where the interesting finding is -- see
`test_bounds_are_non_decreasing_down_every_path`.
"""
from __future__ import annotations

import math
from typing import Dict, List

import pytest

from drp.core.energy import total_energy
from drp.exact.bnb import (CUT_REASONS, NODE_STATUSES, BnBNode, BnBTrace,
                           solve_bnb)
from drp.instances import generate_instance, generate_zone_instance
from drp.meta.construct import best_construction

# Small enough to exhaust, big enough to prune hard.
CASES = [(1, 7, 3), (2, 8, 3), (3, 8, 2), (4, 9, 3)]


def _traced(seed: int, n: int, k: int, **kw) -> tuple:
    inst = generate_instance(f"tr{seed}", n, k, 300 + seed)
    res = solve_bnb(inst, time_limit=kw.pop("time_limit", 60.0),
                    warm_start=best_construction(inst), trace=True, **kw)
    assert res.trace is not None
    return inst, res


def _by_id(trace: BnBTrace) -> Dict[int, BnBNode]:
    return {n.id: n for n in trace.nodes}


def _path_to_root(node: BnBNode, byid: Dict[int, BnBNode]) -> List[BnBNode]:
    chain = [node]
    while chain[-1].parent is not None:
        chain.append(byid[chain[-1].parent])
    return chain


# ---------------------------------------------------------------------------
# 1. completeness
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("seed,n,k", CASES)
def test_node_count_matches_nodes_explored(seed, n, k):
    """One record per `recurse` call -- no more, and none missing."""
    _, res = _traced(seed, n, k, trace_max_nodes=10 ** 9)
    assert not res.trace.truncated
    assert len(res.trace.nodes) == res.nodes_explored
    assert res.trace.nodes_explored == res.nodes_explored
    # ids are the depth-first pre-order index
    assert [x.id for x in res.trace.nodes] == list(range(res.nodes_explored))


@pytest.mark.parametrize("seed,n,k", CASES)
def test_every_node_status_and_candidate_outcome_is_a_declared_one(seed, n, k):
    _, res = _traced(seed, n, k, trace_max_nodes=10 ** 9)
    allowed_out = set(CUT_REASONS) | {"explored", "unexplored"}
    for x in res.trace.nodes:
        assert x.status in NODE_STATUSES, x.status
        for c in x.candidates:
            assert c.outcome in allowed_out, c.outcome
            assert c.kind in ("extend", "open")
            # a geometric/capacity cut has no bound to report, and none is invented
            if c.outcome in ("cut_forbidden", "cut_payload", "cut_battery",
                             "cut_symmetry"):
                assert c.bound is None
            else:
                assert c.bound is not None


# ---------------------------------------------------------------------------
# 2. connectedness
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("seed,n,k", CASES)
def test_every_parent_id_exists(seed, n, k):
    _, res = _traced(seed, n, k, trace_max_nodes=10 ** 9)
    byid = _by_id(res.trace)
    roots = [x for x in res.trace.nodes if x.parent is None]
    assert len(roots) == 1 and roots[0].id == 0
    for x in res.trace.nodes:
        if x.parent is None:
            continue
        assert x.parent in byid, f"node {x.id} has orphan parent {x.parent}"
        assert x.parent < x.id, "pre-order means a parent is recorded first"
        assert x.depth == byid[x.parent].depth + 1


@pytest.mark.parametrize("seed,n,k", CASES)
def test_explored_candidates_name_their_child(seed, n, k):
    """The link the tree explorer draws an edge along must be real in both
    directions: the candidate names a node, and that node names it back."""
    _, res = _traced(seed, n, k, trace_max_nodes=10 ** 9)
    byid = _by_id(res.trace)
    claimed, seen_children = 0, set()
    for x in res.trace.nodes:
        for c in x.candidates:
            if c.outcome != "explored":
                assert c.child is None
                continue
            assert c.child in byid, f"candidate on node {x.id} names no node"
            assert byid[c.child].parent == x.id
            assert c.child not in seen_children, "two parents for one child"
            seen_children.add(c.child)
            claimed += 1
    # every non-root node is claimed by exactly one candidate
    assert claimed == len(res.trace.nodes) - 1


@pytest.mark.parametrize("seed,n,k", CASES)
def test_partial_assignment_is_a_partition_of_the_customers(seed, n, k):
    """closed routes + open route + unassigned must account for every customer
    exactly once -- this is the state the map draws."""
    inst, res = _traced(seed, n, k, trace_max_nodes=10 ** 9)
    everyone = set(range(1, inst.N))
    for x in res.trace.nodes:
        seen = [c for r in x.closed_routes for c in r]
        seen += list(x.open_route) + list(x.unassigned)
        assert sorted(seen) == sorted(everyone), f"node {x.id} loses customers"
        assert len(set(seen)) == len(seen), f"node {x.id} duplicates a customer"


@pytest.mark.parametrize("seed,n,k", CASES)
def test_a_child_state_follows_from_its_parent_and_its_candidate(seed, n, k):
    """`extend` appends to the open route; `open` closes it and starts a new
    one. If the recorded states did not actually compose this way the explorer
    would be animating a tree that never happened."""
    _, res = _traced(seed, n, k, trace_max_nodes=10 ** 9)
    byid = _by_id(res.trace)
    for x in res.trace.nodes:
        for c in x.candidates:
            if c.outcome != "explored":
                continue
            ch = byid[c.child]
            assert sorted(ch.unassigned) == sorted(set(x.unassigned) - {c.customer})
            if c.kind == "extend":
                assert ch.open_route == list(x.open_route) + [c.customer]
                assert ch.closed_routes == x.closed_routes
            else:
                assert ch.open_route == [c.customer]
                expect = [r for r in x.closed_routes]
                if x.open_route:
                    expect = expect + [list(x.open_route)]
                assert ch.closed_routes == expect


# ---------------------------------------------------------------------------
# 3. the bounds behave like bounds
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("seed,n,k", CASES)
def test_pruned_nodes_really_were_dominated(seed, n, k):
    """A node recorded as pruned-by-bound must have a bound at least as large as
    the incumbent it was compared against, using that node's *own* incumbent --
    the one standing at the moment it was reached, not the final one."""
    _, res = _traced(seed, n, k, trace_max_nodes=10 ** 9)
    n_pruned = 0
    for x in res.trace.nodes:
        if x.status != "pruned_bound":
            continue
        n_pruned += 1
        assert x.lower_bound >= x.incumbent - 1e-9, (
            f"node {x.id} claims it was pruned at bound {x.lower_bound} "
            f"against incumbent {x.incumbent}")
    assert n_pruned > 0, "nothing was pruned -- this test proved nothing"


@pytest.mark.parametrize("seed,n,k", CASES)
def test_incumbent_never_worsens_along_the_recorded_order(seed, n, k):
    """Nodes are recorded in the order they were reached, so the incumbent they
    each saw must be monotonically non-increasing."""
    _, res = _traced(seed, n, k, trace_max_nodes=10 ** 9)
    prev = math.inf
    for x in res.trace.nodes:
        assert x.incumbent <= prev + 1e-9, f"incumbent grew at node {x.id}"
        prev = x.incumbent
    if res.optimal:
        assert res.trace.nodes[-1].incumbent >= res.best_energy - 1e-9


@pytest.mark.parametrize("seed,n,k", CASES)
def test_bounds_are_non_decreasing_down_every_path(seed, n, k):
    """A child's bound may not undercut its parent's -- with one exception that
    is real, and is pinned here rather than papered over.

    The exception is the *last* branching step, the one that empties the
    unassigned set. `bounds.assignment_completion_bound` returns 0 for an empty
    completion set, so at that step the bound stops charging the
    return-to-depot arc that the parent's assignment relaxation had priced, and
    can therefore fall by up to that arc's cost. It stays a valid lower bound --
    it only gets looser, never tighter, so the optimum is never pruned, which is
    what `test_bnb_ground_truth.py` verifies end to end -- but it is not
    monotone there.

    So: monotone at every step that leaves work to do, and *only* leaves may
    dip. `test_a_leaf_cost_never_undercuts_an_ancestor_bound` covers what the
    dip could otherwise have hidden.
    """
    _, res = _traced(seed, n, k, trace_max_nodes=10 ** 9)
    byid = _by_id(res.trace)
    dips = 0
    for x in res.trace.nodes:
        if x.parent is None:
            continue
        par = byid[x.parent]
        tol = 1e-6 * max(1.0, abs(par.lower_bound))
        if x.lower_bound >= par.lower_bound - tol:
            continue
        dips += 1
        assert not x.unassigned, (
            f"node {x.id} still has {len(x.unassigned)} customers to place and "
            f"its bound {x.lower_bound} undercuts its parent's "
            f"{par.lower_bound}; only the final step may do that")
    # the root's bound is the floor for the whole search
    root = res.trace.nodes[0]
    assert root.lower_bound == pytest.approx(res.trace.root_bound)
    for x in res.trace.nodes:
        if x.unassigned:
            assert x.lower_bound >= root.lower_bound - 1e-6


@pytest.mark.parametrize("seed,n,k", CASES)
def test_a_leaf_cost_never_undercuts_an_ancestor_bound(seed, n, k):
    """The claim the bounds actually have to support: the realised cost of a
    complete assignment is never below any bound on the way down to it. This is
    what makes pruning sound, and it holds even where the bound itself dips."""
    _, res = _traced(seed, n, k, trace_max_nodes=10 ** 9)
    byid = _by_id(res.trace)
    leaves = 0
    for x in res.trace.nodes:
        if x.committed is None:
            continue
        leaves += 1
        for anc in _path_to_root(x, byid):
            assert x.committed >= anc.lower_bound - 1e-6, (
                f"leaf {x.id} costs {x.committed} but ancestor {anc.id} "
                f"bounded it at {anc.lower_bound}")
    assert leaves > 0


@pytest.mark.parametrize("seed,n,k", CASES)
def test_the_final_incumbent_is_a_recorded_new_incumbent(seed, n, k):
    """Every improvement is recorded, so the explorer's incumbent path is the
    search's own, not a reconstruction."""
    inst, res = _traced(seed, n, k, trace_max_nodes=10 ** 9)
    improvements = [x for x in res.trace.nodes if x.status == "new_incumbent"]
    if res.best_solution is None:
        return
    warm = total_energy(inst, best_construction(inst))
    if res.best_energy < warm - 1e-9:
        assert improvements, "B&B beat its warm start but recorded no improvement"
        best = min(x.committed for x in improvements)
        assert best == pytest.approx(res.best_energy, abs=1e-6)
        # and the routes at that node are the returned solution's routes
        winner = min(improvements, key=lambda x: x.committed)
        routes = [r for r in winner.closed_routes if r]
        if winner.open_route:
            routes.append(list(winner.open_route))
        assert sorted(routes) == sorted(r for r in res.best_solution.routes if r)


# ---------------------------------------------------------------------------
# 4. tracing is free
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("seed,n,k", CASES)
def test_tracing_does_not_change_the_answer(seed, n, k):
    """The whole point of an opt-in hook: identical solution, identical energy,
    identical node count, identical bound."""
    inst = generate_instance(f"tr{seed}", n, k, 300 + seed)
    ws = best_construction(inst)
    off = solve_bnb(inst, time_limit=60.0, warm_start=ws.copy())
    on = solve_bnb(inst, time_limit=60.0, warm_start=ws.copy(), trace=True)

    assert on.best_energy == off.best_energy
    assert on.best_solution.routes == off.best_solution.routes
    assert on.nodes_explored == off.nodes_explored
    assert on.dual_bound == off.dual_bound
    assert on.optimal == off.optimal
    assert on.timed_out == off.timed_out
    assert off.trace is None, "tracing must be off by default"


def test_tracing_is_off_by_default_and_costs_nothing_structurally():
    inst = generate_instance("default", 8, 3, 321)
    res = solve_bnb(inst, time_limit=20.0, warm_start=best_construction(inst))
    assert res.trace is None


def test_a_capped_trace_truncates_the_record_not_the_search():
    """The cap exists so a large instance cannot exhaust memory. It must bound
    the recording only -- the search itself has to run to completion."""
    inst = generate_instance("cap", 9, 3, 303)
    ws = best_construction(inst)
    full = solve_bnb(inst, time_limit=120.0, warm_start=ws.copy(), trace=True,
                     trace_max_nodes=10 ** 9)
    assert full.nodes_explored > 500, "pick a harder instance for this test"

    capped = solve_bnb(inst, time_limit=120.0, warm_start=ws.copy(), trace=True,
                       trace_max_nodes=200)
    assert capped.trace.truncated
    assert len(capped.trace.nodes) == 200
    assert capped.trace.nodes_explored == capped.nodes_explored
    # the search is untouched
    assert capped.nodes_explored == full.nodes_explored
    assert capped.best_energy == full.best_energy
    assert capped.best_solution.routes == full.best_solution.routes
    # a truncated trace is still a well-formed tree: pre-order is closed under
    # "parent of", so nothing is orphaned
    byid = _by_id(capped.trace)
    for x in capped.trace.nodes:
        assert x.parent is None or x.parent in byid
    assert [x.id for x in capped.trace.nodes] == list(range(200))


def test_trace_survives_a_timeout():
    """A run cut off by the clock must still hand back a usable tree, with the
    node the clock stopped at marked as such."""
    inst = generate_instance("slow", 12, 4, 11)
    res = solve_bnb(inst, time_limit=0.25, warm_start=best_construction(inst),
                    trace=True, trace_max_nodes=10 ** 9)
    if not res.timed_out:
        pytest.skip("instance finished inside the limit")
    assert res.trace.nodes
    assert any(x.status == "timeout" for x in res.trace.nodes)
    byid = _by_id(res.trace)
    for x in res.trace.nodes:
        assert x.parent is None or x.parent in byid
    # candidates generated but never entered are reported honestly
    unexplored = [c for x in res.trace.nodes for c in x.candidates
                  if c.outcome == "unexplored"]
    assert all(c.child is None for c in unexplored)


def test_trace_on_a_zone_instance_is_well_formed():
    """Polygonal zones change the distance matrix, not the branching -- the
    trace must be just as sound there, since that is the instance the explorer's
    map is most interesting on."""
    inst = generate_zone_instance("ztrace", 8, 3, seed=2026, n_zones=2)
    res = solve_bnb(inst, time_limit=60.0, warm_start=best_construction(inst),
                    trace=True, trace_max_nodes=10 ** 9)
    assert len(res.trace.nodes) == res.nodes_explored
    byid = _by_id(res.trace)
    for x in res.trace.nodes:
        assert x.parent is None or x.parent in byid
        if x.status == "pruned_bound":
            assert x.lower_bound >= x.incumbent - 1e-9


def test_trace_to_dict_is_json_safe():
    """The payload crosses into the browser as JSON, which has no Infinity: an
    absent incumbent must serialise as null rather than as a number."""
    import json

    inst = generate_instance("json", 7, 3, 55)
    res = solve_bnb(inst, time_limit=30.0, trace=True)   # no warm start
    d = res.trace.to_dict()
    text = json.dumps(d)          # raises on inf/nan only via allow_nan=False
    json.dumps(d, allow_nan=False)
    assert "Infinity" not in text and "NaN" not in text
    assert d["nodes"][0]["incumbent"] is None, \
        "without a warm start the root has no incumbent, and must say so"
    assert d["nodes_explored"] == res.nodes_explored
    assert len(d["nodes"]) == len(res.trace.nodes)
