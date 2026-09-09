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
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from drp.core.energy import route_energy, route_energy_open, route_weight, total_energy
from drp.core.feasibility import is_feasible
from drp.core.instance import DRPInstance
from drp.core.solution import Solution
from drp.exact.bounds import (assignment_completion_bound, completion_bound,
                               min_in_edge)


@dataclass
class BnBResult:
    best_solution: Optional[Solution] = None
    best_energy: float = math.inf
    dual_bound: float = 0.0
    nodes_explored: int = 0
    optimal: bool = False
    timed_out: bool = False
    time: float = 0.0

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
# unassigned, closed_energy, lower_bound)
_Child = Tuple[List[List[int]], List[int], frozenset, float, float]


def solve_bnb(inst: DRPInstance,
              time_limit: float = 30.0,
              warm_start: Optional[Solution] = None) -> BnBResult:
    res = BnBResult()
    t0 = time.time()
    min_in = min_in_edge(inst)
    timed_out = [False]

    # Bounds of every frontier node: generated, never expanded.
    frontier: List[float] = []

    if warm_start is not None:
        ok, _ = is_feasible(inst, warm_start)
        if ok:
            res.best_solution = warm_start.copy()
            res.best_energy = total_energy(inst, warm_start)

    full = frozenset(range(1, inst.N))
    root_bound = max(completion_bound(min_in, full),
                     assignment_completion_bound(inst, None, full, inst.n_drones))

    def recurse(routes: List[List[int]],
                open_route: List[int],
                unassigned: frozenset,
                closed_energy: float,
                lb: float) -> None:
        res.nodes_explored += 1

        if lb >= res.best_energy - 1e-9:
            return  # sterile: nothing under here can beat the incumbent

        if not unassigned:
            all_routes = routes + ([open_route] if open_route else [])
            sol = Solution([r[:] for r in all_routes]
                           + [[]] * (inst.n_drones - len(all_routes)))
            ok, _ = is_feasible(inst, sol)
            committed = closed_energy + (route_energy(inst, open_route)
                                         if open_route else 0.0)
            if ok and committed < res.best_energy - 1e-9:
                res.best_energy = committed
                res.best_solution = sol
            return

        if time.time() - t0 > time_limit:
            timed_out[0] = True
            frontier.append(lb)   # this subtree is unexplored
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

        def bound_child(base: float, rest: frozenset, cheap_rest: float,
                        child_prev: int, child_routes_left: int) -> Optional[float]:
            cheap_lb = base + cheap_rest
            if cheap_lb >= res.best_energy - 1e-9:
                return None  # sterile against the cheap bound alone
            if not rest:
                return cheap_lb
            ap_rest = assignment_completion_bound(inst, child_prev, rest,
                                                  child_routes_left)
            return base + max(cheap_rest, ap_rest)

        # Branch A: extend the open route.
        if open_route:
            prev = open_route[-1]
            for c in sorted(unassigned):
                if inst.edge_forbidden(prev, c):
                    continue
                trial = open_route + [c]
                if route_weight(inst, trial) > inst.payload + 1e-9:
                    continue
                if route_energy(inst, trial) > inst.battery + 1e-9:
                    continue
                rest = unassigned - {c}
                child_lb = bound_child(closed_energy + route_energy_open(inst, trial),
                                       rest, comp - min_in[c], c, routes_left)
                if child_lb is not None:
                    children.append((routes, trial, rest, closed_energy, child_lb))

        # Branch B: close the open route, open a new one (symmetry-broken).
        if drones_used < inst.n_drones:
            new_routes = routes + ([open_route] if open_route else [])
            new_closed = closed_energy + (route_energy(inst, open_route)
                                          if open_route else 0.0)
            min_first = new_routes[-1][0] if new_routes and new_routes[-1] else 0
            for c in sorted(unassigned):
                if c <= min_first or inst.edge_forbidden(0, c):
                    continue
                single = [c]
                if route_weight(inst, single) > inst.payload + 1e-9:
                    continue
                if route_energy(inst, single) > inst.battery + 1e-9:
                    continue
                rest = unassigned - {c}
                child_lb = bound_child(new_closed + route_energy_open(inst, single),
                                       rest, comp - min_in[c], c, routes_left - 1)
                if child_lb is not None:
                    children.append((new_routes, single, rest, new_closed, child_lb))

        # Explore depth-first, cheapest bound first. If the clock runs out
        # part-way, every child we never entered joins the frontier.
        children.sort(key=lambda ch: ch[4])
        for idx, ch in enumerate(children):
            if timed_out[0]:
                frontier.extend(x[4] for x in children[idx:])
                return
            recurse(*ch)

    recurse([], [], full, 0.0, root_bound)

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
