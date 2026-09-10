"""Data payload for the B&B tree explorer (roadmap §2.4).

Same split as `drp/viz/webdata.py`, deliberately: Python emits one JSON dict,
every layout decision, tween and camera move lives in
`drp/viz/web/tree_template.html`. Nothing here decides how the tree *looks* --
not the node positions, not the colour ramp, not the scrubber -- because the
moment Python starts laying out a tree, the two halves have to agree on a
coordinate system and the split stops paying for itself.

What Python does contribute is the geometry the browser cannot recompute: the
flown path between each pair of nodes, detoured around any polygonal no-fly zone
by `drp.geometry.visibility.shortest_path`. That is the same helper
`drp.viz.static.route_polyline` uses, so a partial route drawn in the explorer
bends around a zone exactly the way the finished route does in the flight
replay. The table is over unordered pairs (paths are symmetric) and is only
built for pairs a *recorded* node actually uses, so it stays small even when the
instance does not.

Everything else is the trace as the solver recorded it (`BnBTrace.to_dict`),
plus the aggregate result. No search state is reconstructed or inferred here.
The one derived series the page draws -- the dual bound closing on the incumbent
-- is computed in the browser from the trace's own frontier, by exactly the rule
`solve_bnb` uses for its reported `dual_bound`: the minimum bound over every
node that has been generated but not yet expanded.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from drp.core.instance import DRPInstance
from drp.core.solution import Solution
from drp.exact.bnb import BnBResult
from drp.instances.io import instance_to_dict, solution_to_dict
from drp.viz.static import PALETTE


def _pair_key(i: int, j: int) -> str:
    a, b = (i, j) if i <= j else (j, i)
    return f"{a}-{b}"


def leg_paths(inst: DRPInstance,
              pairs: Sequence[Tuple[int, int]]) -> Dict[str, List[List[float]]]:
    """The flown path for each unordered node pair, detour-aware.

    Straight lines when the instance has no polygonal zones; the visibility
    graph's shortest path when it does. Endpoints are always included, so the
    browser can concatenate legs into a route without knowing anything about
    the geometry.
    """
    out: Dict[str, List[List[float]]] = {}
    co = inst.coords
    use_zones = bool(inst.nofly_zones)
    if use_zones:
        from drp.geometry.visibility import shortest_path

    for i, j in pairs:
        key = _pair_key(i, j)
        if key in out:
            continue
        a, b = (i, j) if i <= j else (j, i)
        if use_zones:
            seg = shortest_path(inst.coords, inst.nofly_zones, a, b)
            pts = [[float(p[0]), float(p[1])] for p in seg]
        else:
            pts = [[float(co[a][0]), float(co[a][1])],
                   [float(co[b][0]), float(co[b][1])]]
        out[key] = pts
    return out


def _pairs_used(trace_nodes: Sequence[Any]) -> Set[Tuple[int, int]]:
    """Every node pair the explorer can be asked to draw.

    That is: the legs of every partial route in the trace (including the
    return-to-depot leg a *closed* route has flown), plus one leg per candidate
    -- the ghost stroke Solver Vision draws for an option that was rejected.
    """
    pairs: Set[Tuple[int, int]] = set()

    def walk(route: Sequence[int], closed: bool) -> None:
        prev = 0
        for c in route:
            pairs.add((prev, c))
            prev = c
        if closed and route:
            pairs.add((prev, 0))

    for n in trace_nodes:
        for r in n.closed_routes:
            walk(r, True)
        walk(n.open_route, False)
        tip = n.open_route[-1] if n.open_route else 0
        for cand in n.candidates:
            pairs.add((tip if cand.kind == "extend" else 0, cand.customer))
    return pairs


def build_tree_data(inst: DRPInstance,
                    res: BnBResult,
                    title: Optional[str] = None) -> Dict[str, Any]:
    """Everything the tree explorer needs, as one JSON-serialisable dict.

    `res` must come from ``solve_bnb(..., trace=True)``; without a trace there
    is nothing to explore and this raises rather than drawing an empty tree.
    """
    if res.trace is None:
        raise ValueError(
            "BnBResult carries no trace; call solve_bnb(..., trace=True)")

    nodes = res.trace.nodes
    paths = leg_paths(inst, sorted(_pairs_used(nodes)))

    co = inst.coords
    sol_dict = (solution_to_dict(inst, res.best_solution, method="bnb")
                if res.best_solution is not None else None)

    return {
        "instance": instance_to_dict(inst),
        "solution": sol_dict,
        "trace": res.trace.to_dict(),
        "paths": paths,
        "result": {
            "best_energy": (None if math.isinf(res.best_energy)
                            else float(res.best_energy)),
            "dual_bound": (None if math.isinf(res.dual_bound)
                           else float(res.dual_bound)),
            "gap": (None if math.isinf(res.gap) else float(res.gap)),
            "nodes_explored": int(res.nodes_explored),
            "optimal": bool(res.optimal),
            "timed_out": bool(res.timed_out),
            "time": float(res.time),
            "summary": res.summary(),
        },
        "meta": {
            "title": title or f"{inst.name} -- branch & bound",
            "palette": list(PALETTE),
            "bounds": {
                "xmin": float(co[:, 0].min()), "xmax": float(co[:, 0].max()),
                "ymin": float(co[:, 1].min()), "ymax": float(co[:, 1].max()),
            },
            "zones": [[[float(x), float(y)] for x, y in poly]
                      for poly in inst.nofly_zones],
        },
    }


def build_vision_data(inst: DRPInstance,
                      sol: Solution,
                      res: BnBResult) -> Dict[str, Any]:
    """Solver Vision for the flight replay (roadmap §2.4, step 4).

    For each route in `sol` and each prefix of that route, find the trace node
    whose open route *is* that prefix -- i.e. the moment the search stood
    exactly where this drone stands -- and hand back the options that node
    considered and rejected. The replay draws those as thin ghost legs against
    the leg actually flown.

    This deliberately does not require `sol` to be the trace's own optimum. A
    replay of an ALNS solution against a B&B trace is a legitimate thing to
    want, and where the search never stood at a given prefix there simply is no
    entry -- `matched` and `total` report that honestly rather than the page
    inventing an alternative that was never considered.
    """
    if res.trace is None:
        raise ValueError(
            "BnBResult carries no trace; call solve_bnb(..., trace=True)")

    # First (lowest-id) node standing at each open-route prefix. Lowest id is
    # the first time the search reached that state, which is the one whose
    # candidate list is complete rather than already narrowed by a better
    # incumbent found later.
    by_prefix: Dict[Tuple[int, ...], Any] = {}
    for n in res.trace.nodes:
        key = tuple(n.open_route)
        if key not in by_prefix:
            by_prefix[key] = n

    steps: List[Dict[str, Any]] = []
    matched = total = 0
    for k, route in enumerate(sol.routes):
        if not route:
            continue
        for i in range(len(route)):
            prefix = tuple(route[:i + 1])
            total += 1
            n = by_prefix.get(prefix)
            if n is None:
                continue
            matched += 1
            tip = prefix[-2] if len(prefix) > 1 else 0
            rejected = [{
                "customer": int(c.customer),
                "kind": c.kind,
                "outcome": c.outcome,
                "bound": c.bound,
                "from": (n.open_route[-1] if (c.kind == "extend" and n.open_route)
                         else 0),
            } for c in n.candidates if c.outcome != "explored"]
            steps.append({
                "drone": int(k),
                "index": i,
                "customer": int(prefix[-1]),
                "from": int(tip),
                "node": int(n.id),
                "depth": int(n.depth),
                "lower_bound": n.lower_bound if math.isfinite(n.lower_bound) else None,
                "incumbent": n.incumbent if math.isfinite(n.incumbent) else None,
                "rejected": rejected,
            })

    pairs: Set[Tuple[int, int]] = set()
    for s in steps:
        for r in s["rejected"]:
            pairs.add((r["from"], r["customer"]))

    return {
        "steps": steps,
        "paths": leg_paths(inst, sorted(pairs)),
        "matched": matched,
        "total": total,
        "nodes_explored": int(res.nodes_explored),
        "optimal": bool(res.optimal),
        "best_energy": (None if math.isinf(res.best_energy)
                        else float(res.best_energy)),
        "truncated": bool(res.trace.truncated),
    }
