"""Exact method: depth-first Branch & Bound over partitions into ordered routes.

Branching
---------
At each node we either (A) append an unassigned customer to the currently open
route, or (B) close the open route and start a new one, consuming a drone.
Successive routes are forced to start with strictly increasing first-customer
indices -- a symmetry break that generates each partition-into-ordered-routes
exactly once.

Bounding and pruning
--------------------
Two bounds, cheap-first (roadmap §5.1). `bounds.min_in_edge` gives an O(1)
completion estimate; a child that is already sterile against it is dropped
without further work. A child that survives is re-bounded with
`bounds.assignment_completion_bound`, an assignment-relaxation (Hungarian
algorithm) bound that cannot be fooled the way the column-minimum sum can --
see `bounds.py` for why it strictly dominates. The reported bound is the
better of the two. A node is discarded when ``committed + completion >=
incumbent`` (a sterile set), and also on any payload, battery or no-fly
violation.

**A subtlety that tightening the completion bound exposed.** ``committed``
for the still-open route must be `route_energy_open`, not `route_energy`:
the latter bakes in a return-to-depot leg from whichever customer is
currently last, as if the route stopped right there. If the route goes on to
take more customers, that leg is never actually flown -- it is replaced by a
longer path through the rest of the route -- so charging it is phantom cost
with no lower-bound justification. Once the completion term was tight enough
(the assignment-relaxation bound below), phantom-return-plus-completion could
exceed the true remaining cost and prune the actual optimum, still exhausting
the tree and reporting a wrong answer labelled "proven optimal".
`test_bnb_ground_truth.py` caught it directly (`res.best_energy` above the
brute-forced truth) before this was fixed. The real return leg is charged
exactly once: at the moment a route actually closes (`route_energy` on a
route that is genuinely done), or inside `assignment_completion_bound`,
which prices every candidate closing arc as one of its own options.

Anytime dual bound (roadmap §5.1)
---------------------------------
A depth-first search cut off by its time limit used to report only its
incumbent -- which, warm-started from greedy, was often *still* the greedy
value, with nothing to say about how good it was. We now report a valid global
lower bound as well, so every run yields a real optimality gap:

    dual_bound <= optimum <= best_energy

Getting this right needs care. It is **not** enough to record the bound of the
node we happened to be sitting in when the clock ran out: the unexplored space
also contains every sibling we had not reached yet, and those may be cheaper.
The valid bound is the minimum over the whole *frontier* -- every node that was
generated but never expanded.

So each frame materialises its children with their bounds before descending. If
time expires mid-subtree, the frame contributes the bounds of the children it
never entered, and the node that actually timed out contributes its own. Nodes
pruned as sterile contribute nothing, correctly: their bound already exceeds the
incumbent, so nothing better hides beneath them. The minimum over that frontier
is a true lower bound on the optimum.

When the tree is exhausted the bound meets the incumbent and `optimal` is True.

Trace instrumentation (roadmap §2.4)
------------------------------------
`solve_bnb(..., trace=True)` additionally records the search itself, so the tree
explorer (`drp/viz/webtree.py`) can show *why the search never went down most of
the tree*. It is opt-in and costs nothing when off: every recording site sits
behind a single ``tr is not None`` test, and `bench`/`compare` -- which run under
a time limit and must not regress -- never enable it.

One `BnBNode` is recorded per call to `recurse`, so ``len(trace.nodes)`` equals
`nodes_explored` exactly (until the cap below bites). Each carries the partial
assignment at that node, its lower bound, the incumbent *at that moment*, and how
it ended: `expanded`, `pruned_bound`, `infeasible`, `new_incumbent`, `dominated`
(a complete, feasible assignment that did not beat the incumbent) or `timeout`.

Each node also lists every branching option it *considered*, including the ones
that never became nodes at all -- rejected for a forbidden arc, an over-payload
or over-battery route, the symmetry break, or a sterile bound. Those rejections
are the bulk of the pruning and are invisible in `nodes_explored`; they are what
"Solver Vision" in the flight replay draws as candidate routes.

The trace is capped at `trace_max_nodes` records. Recording simply stops at the
cap and `trace.truncated` is set -- the *search* is untouched, so a capped run
returns exactly what an untraced one returns. Because nodes are recorded in
depth-first pre-order and ids are pre-order indices, the recorded prefix is
closed under "parent of", so every recorded node's parent is recorded too.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from drp.core.energy import route_energy, route_energy_open, route_weight, total_energy
from drp.core.feasibility import is_feasible
from drp.core.instance import DRPInstance
from drp.core.solution import Solution
from drp.exact.bounds import (assignment_completion_bound, completion_bound,
                               min_in_edge)


# --- trace records (roadmap §2.4) ------------------------------------------
# Populated only when `solve_bnb(..., trace=True)`. Nothing here is inferred:
# every field is read straight off the search as it happens.

#: Why a branching option never became a node.
CUT_REASONS = ("cut_forbidden", "cut_payload", "cut_battery", "cut_symmetry",
               "cut_bound")
#: How a node that *was* entered ended.
NODE_STATUSES = ("expanded", "pruned_bound", "infeasible", "new_incumbent",
                 "dominated", "timeout")


@dataclass
class BnBCandidate:
    """One branching option a node considered, and what became of it.

    `kind` is ``"extend"`` (append `customer` to the open route) or ``"open"``
    (close the open route and start a new one at `customer`). `outcome` is
    ``"explored"``, ``"unexplored"`` (generated, but the clock ran out before we
    reached it) or one of `CUT_REASONS`. `bound` is the child's lower bound
    where one was computed -- for `cut_bound` that is the cheap bound that
    condemned it, and for the geometric/capacity cuts there is none, so it stays
    None rather than being invented.
    """
    kind: str
    customer: int
    outcome: str
    bound: Optional[float] = None
    child: Optional[int] = None      # id of the node this became, if explored


@dataclass
class BnBNode:
    """One call to `recurse`: the partial assignment and how it ended."""
    id: int
    parent: Optional[int]
    depth: int
    closed_routes: List[List[int]]
    open_route: List[int]
    unassigned: List[int]
    lower_bound: float
    incumbent: float                 # the incumbent *at this moment*
    status: str = "expanded"
    committed: Optional[float] = None   # leaf only: the complete route cost
    candidates: List[BnBCandidate] = field(default_factory=list)


@dataclass
class BnBTrace:
    """The recorded search. `nodes` is in depth-first pre-order; `id` is the
    pre-order index, so ``nodes[i].id == i`` on an untruncated trace."""
    nodes: List[BnBNode] = field(default_factory=list)
    max_nodes: int = 20000
    truncated: bool = False
    root_bound: float = 0.0
    nodes_explored: int = 0          # total recursed; > len(nodes) if truncated

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe form. Infinities become None -- JSON has no ``Infinity``,
        and a missing incumbent is genuinely 'none yet', not a number."""
        def f(v: Optional[float]) -> Optional[float]:
            if v is None or not math.isfinite(v):
                return None
            return float(v)

        return {
            "root_bound": f(self.root_bound),
            "max_nodes": self.max_nodes,
            "truncated": self.truncated,
            "nodes_explored": self.nodes_explored,
            "nodes": [{
                "id": n.id,
                "parent": n.parent,
                "depth": n.depth,
                "closed_routes": [[int(c) for c in r] for r in n.closed_routes],
                "open_route": [int(c) for c in n.open_route],
                "unassigned": [int(c) for c in n.unassigned],
                "lower_bound": f(n.lower_bound),
                "incumbent": f(n.incumbent),
                "status": n.status,
                "committed": f(n.committed),
                "candidates": [{
                    "kind": c.kind, "customer": int(c.customer),
                    "outcome": c.outcome, "bound": f(c.bound), "child": c.child,
                } for c in n.candidates],
            } for n in self.nodes],
        }


@dataclass
class BnBResult:
    best_solution: Optional[Solution] = None
    best_energy: float = math.inf
    dual_bound: float = 0.0
    nodes_explored: int = 0
    optimal: bool = False
    timed_out: bool = False
    time: float = 0.0
    trace: Optional[BnBTrace] = None

    @property
    def gap(self) -> float:
        """Relative optimality gap in percent, ``(UB - LB) / UB``.

        Zero when the search finished, i.e. the answer is proven optimal.
        """
        if self.best_energy in (0.0, math.inf) or math.isinf(self.dual_bound):
            return math.inf
        return 100.0 * (self.best_energy - self.dual_bound) / self.best_energy

    def summary(self) -> str:
        if self.optimal:
            return (f"proven optimal E={self.best_energy:.1f} "
                    f"({self.nodes_explored} nodes, {self.time:.2f}s)")
        return (f"E={self.best_energy:.1f} LB={self.dual_bound:.1f} "
                f"gap={self.gap:.1f}% ({self.nodes_explored} nodes, "
                f"{self.time:.2f}s, timed out)")


# A generated-but-not-yet-expanded child: (closed_routes, open_route,
# unassigned, closed_energy, lower_bound, trace_record_or_None)
_Child = Tuple[List[List[int]], List[int], frozenset, float, float,
               Optional[BnBCandidate]]


def solve_bnb(inst: DRPInstance,
              time_limit: float = 30.0,
              warm_start: Optional[Solution] = None,
              trace: bool = False,
              trace_max_nodes: int = 20000) -> BnBResult:
    """Solve `inst` exactly, or as far as `time_limit` allows.

    `trace=True` additionally records the search into `BnBResult.trace` (see the
    module docstring). It does not change the search: the same nodes are
    explored in the same order and the same solution comes back, capped trace or
    not. `trace_max_nodes` bounds the recording, not the search.
    """
    res = BnBResult()
    t0 = time.time()
    min_in = min_in_edge(inst)
    timed_out = [False]

    # Bounds of every frontier node: generated, never expanded.
    frontier: List[float] = []

    tr: Optional[BnBTrace] = None
    if trace:
        tr = BnBTrace(max_nodes=max(1, int(trace_max_nodes)))
        res.trace = tr

    if warm_start is not None:
        ok, _ = is_feasible(inst, warm_start)
        if ok:
            res.best_solution = warm_start.copy()
            res.best_energy = total_energy(inst, warm_start)

    full = frozenset(range(1, inst.N))
    root_bound = max(completion_bound(min_in, full),
                     assignment_completion_bound(inst, None, full, inst.n_drones))
    if tr is not None:
        tr.root_bound = root_bound

    def recurse(routes: List[List[int]],
                open_route: List[int],
                unassigned: frozenset,
                closed_energy: float,
                lb: float,
                parent: Optional[int] = None,
                depth: int = 0) -> None:
        nid = res.nodes_explored
        res.nodes_explored += 1

        rec: Optional[BnBNode] = None
        if tr is not None:
            if len(tr.nodes) < tr.max_nodes:
                rec = BnBNode(id=nid, parent=parent, depth=depth,
                              closed_routes=[r[:] for r in routes],
                              open_route=open_route[:],
                              unassigned=sorted(unassigned),
                              lower_bound=lb,
                              incumbent=res.best_energy)
                tr.nodes.append(rec)
            else:
                tr.truncated = True

        if lb >= res.best_energy - 1e-9:
            if rec is not None:
                rec.status = "pruned_bound"
            return  # sterile: nothing under here can beat the incumbent

        if not unassigned:
            all_routes = routes + ([open_route] if open_route else [])
            sol = Solution([r[:] for r in all_routes]
                           + [[]] * (inst.n_drones - len(all_routes)))
            ok, _ = is_feasible(inst, sol)
            committed = closed_energy + (route_energy(inst, open_route)
                                         if open_route else 0.0)
            improved = ok and committed < res.best_energy - 1e-9
            if improved:
                res.best_energy = committed
                res.best_solution = sol
            if rec is not None:
                rec.committed = committed
                rec.status = ("new_incumbent" if improved
                              else "infeasible" if not ok else "dominated")
            return

        if time.time() - t0 > time_limit:
            timed_out[0] = True
            frontier.append(lb)   # this subtree is unexplored
            if rec is not None:
                rec.status = "timeout"
            return

        # Completion cost of the current unassigned set. Because the bound is a
        # plain sum, a child's completion is this minus the served customer's
        # term -- O(1) instead of O(n). Used as a cheap pre-filter: a child
        # already sterile against it is dropped before paying for the
        # Hungarian-algorithm bound below.
        comp = completion_bound(min_in, unassigned)
        drones_used = len(routes) + (1 if open_route else 0)
        routes_left = inst.n_drones - drones_used
        children: List[_Child] = []

        # Returns ``(lower_bound, survives)``. The bound comes back even when
        # the child is condemned, so the trace can say *what* condemned it --
        # `survives` is exactly the old "not None" test, so the set of children
        # generated, and therefore `nodes_explored`, is unchanged.
        def bound_child(base: float, rest: frozenset, cheap_rest: float,
                        child_prev: int,
                        child_routes_left: int) -> Tuple[float, bool]:
            cheap_lb = base + cheap_rest
            if cheap_lb >= res.best_energy - 1e-9:
                return cheap_lb, False  # sterile against the cheap bound alone
            if not rest:
                return cheap_lb, True
            ap_rest = assignment_completion_bound(inst, child_prev, rest,
                                                  child_routes_left)
            return base + max(cheap_rest, ap_rest), True

        def note(kind: str, c: int, outcome: str,
                 bound: Optional[float] = None) -> Optional[BnBCandidate]:
            if rec is None:
                return None
            cand = BnBCandidate(kind=kind, customer=c, outcome=outcome,
                                bound=bound)
            rec.candidates.append(cand)
            return cand

        # Branch A: extend the open route.
        if open_route:
            prev = open_route[-1]
            for c in sorted(unassigned):
                if inst.edge_forbidden(prev, c):
                    note("extend", c, "cut_forbidden")
                    continue
                trial = open_route + [c]
                if route_weight(inst, trial) > inst.payload + 1e-9:
                    note("extend", c, "cut_payload")
                    continue
                if route_energy(inst, trial) > inst.battery + 1e-9:
                    note("extend", c, "cut_battery")
                    continue
                rest = unassigned - {c}
                child_lb, ok = bound_child(
                    closed_energy + route_energy_open(inst, trial),
                    rest, comp - min_in[c], c, routes_left)
                cand = note("extend", c,
                            "explored" if ok else "cut_bound", child_lb)
                if ok:
                    children.append((routes, trial, rest, closed_energy,
                                     child_lb, cand))

        # Branch B: close the open route, open a new one (symmetry-broken).
        if drones_used < inst.n_drones:
            new_routes = routes + ([open_route] if open_route else [])
            new_closed = closed_energy + (route_energy(inst, open_route)
                                          if open_route else 0.0)
            min_first = new_routes[-1][0] if new_routes and new_routes[-1] else 0
            for c in sorted(unassigned):
                if c <= min_first:
                    note("open", c, "cut_symmetry")
                    continue
                if inst.edge_forbidden(0, c):
                    note("open", c, "cut_forbidden")
                    continue
                single = [c]
                if route_weight(inst, single) > inst.payload + 1e-9:
                    note("open", c, "cut_payload")
                    continue
                if route_energy(inst, single) > inst.battery + 1e-9:
                    note("open", c, "cut_battery")
                    continue
                rest = unassigned - {c}
                child_lb, ok = bound_child(
                    new_closed + route_energy_open(inst, single),
                    rest, comp - min_in[c], c, routes_left - 1)
                cand = note("open", c,
                            "explored" if ok else "cut_bound", child_lb)
                if ok:
                    children.append((new_routes, single, rest, new_closed,
                                     child_lb, cand))

        # Explore depth-first, cheapest bound first. If the clock runs out
        # part-way, every child we never entered joins the frontier.
        children.sort(key=lambda ch: ch[4])
        for idx, ch in enumerate(children):
            if timed_out[0]:
                frontier.extend(x[4] for x in children[idx:])
                for x in children[idx:]:
                    if x[5] is not None:
                        x[5].outcome = "unexplored"
                return
            if ch[5] is not None:
                ch[5].child = res.nodes_explored   # the id `recurse` will take
            recurse(ch[0], ch[1], ch[2], ch[3], ch[4], nid, depth + 1)

    recurse([], [], full, 0.0, root_bound)

    if tr is not None:
        tr.nodes_explored = res.nodes_explored

    res.time = time.time() - t0
    res.timed_out = timed_out[0]
    res.optimal = (not timed_out[0]) and (res.best_solution is not None)

    if res.optimal:
        res.dual_bound = res.best_energy
    elif frontier:
        res.dual_bound = min(frontier)
    else:
        res.dual_bound = root_bound
    # The bound is only interesting up to the incumbent.
    res.dual_bound = min(res.dual_bound, res.best_energy)
    return res
