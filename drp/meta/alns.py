"""Adaptive Large Neighbourhood Search (roadmap §5.2).

The modern workhorse for routing. Where SA perturbs a tour by one small move,
ALNS repeatedly *destroys* a sizeable chunk of the solution and *repairs* it,
which moves through the search space in far larger and better-directed steps.

Operators
---------
Destroy (remove ``q`` customers from the giant tour):

  * ``random_removal``  -- uniform; pure diversification.
  * ``worst_removal``   -- drop the customers contributing most marginal energy,
    on the theory that they are badly placed.
  * ``shaw_removal``    -- drop a seed customer and its nearest relatives, so the
    repair gets a real chance to re-group a whole neighbourhood.
  * ``route_removal``   -- empty one whole drone route, forcing its customers to
    be redistributed.

Repair (re-insert the removed customers):

  * ``greedy_insert``   -- each customer into its cheapest position, cheapest
    customer first.
  * ``regret_2`` / ``regret_3`` -- insert the customer that would suffer most if
    it had to wait, measured as the gap between its best and k-th best position.
    Look-ahead that plain greedy lacks.

Adaptivity
----------
Each operator carries a weight. After every segment of iterations the weights
are updated from the scores earned that segment -- a large reward for finding a
new global best, less for an improving or merely accepted move -- so operators
that are working get chosen more often. Acceptance is simulated-annealing style,
so ALNS can still escape local optima.

Feasibility is delegated to Split exactly as in the GA and SA, so all three
search the same space and are directly comparable.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from drp.core.instance import DRPInstance
from drp.core.solution import Solution
from drp.meta.construct import warm_start_tour
from drp.meta.encoding import random_tour
from drp.meta.split import split
from drp.meta.trace import MetaSample, MetaSegment, MetaTrace, MetaTracer

# Scores awarded to the operators that produced a move.
SCORE_NEW_BEST = 33.0
SCORE_IMPROVED = 13.0
SCORE_ACCEPTED = 9.0


@dataclass
class ALNSResult:
    best_solution: Optional[Solution] = None
    best_energy: float = math.inf
    history: List[float] = field(default_factory=list)
    iterations: int = 0
    time: float = 0.0
    destroy_weights: dict = field(default_factory=dict)
    repair_weights: dict = field(default_factory=dict)
    trace: Optional[MetaTrace] = None
    #: ``(seconds, energy)`` at the start and at every new best -- the anytime
    #: curve (roadmap §6). Always on; appended only when the best improves.
    anytime: List[Tuple[float, float]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Destroy operators: return (remaining_tour, removed_customers)
# ---------------------------------------------------------------------------
def random_removal(inst, tour, q, rng):
    idx = set(rng.sample(range(len(tour)), q))
    removed = [tour[i] for i in sorted(idx)]
    return [c for i, c in enumerate(tour) if i not in idx], removed


def worst_removal(inst, tour, q, rng):
    """Remove the customers whose presence costs the most.

    Cost is measured by detour: how much shorter the tour's local geometry gets
    if the customer is skipped.
    """
    d = inst.dist
    n = len(tour)
    costs = []
    for i, c in enumerate(tour):
        prev = tour[i - 1] if i > 0 else 0
        nxt = tour[i + 1] if i + 1 < n else 0
        costs.append((d[prev, c] + d[c, nxt] - d[prev, nxt], i))
    costs.sort(reverse=True)
    # a little randomisation so the operator is not fully deterministic
    picks = costs[:max(q, min(n, q + 2))]
    rng.shuffle(picks)
    idx = {i for _, i in picks[:q]}
    removed = [tour[i] for i in sorted(idx)]
    return [c for i, c in enumerate(tour) if i not in idx], removed


def shaw_removal(inst, tour, q, rng):
    """Remove a seed customer together with its nearest neighbours."""
    d = inst.dist
    seed = rng.choice(tour)
    ranked = sorted(tour, key=lambda c: d[seed, c])
    chosen = set(ranked[:q])
    removed = [c for c in tour if c in chosen]
    return [c for c in tour if c not in chosen], removed


def route_removal(inst, tour, q, rng):
    """Empty one whole drone route, redistributing its customers."""
    sol, e = split(inst, tour)
    if sol is None:
        return random_removal(inst, tour, q, rng)
    used = sol.used_routes()
    if not used:
        return random_removal(inst, tour, q, rng)
    victim = set(rng.choice(used))
    removed = [c for c in tour if c in victim]
    remaining = [c for c in tour if c not in victim]
    if not remaining or not removed:
        return random_removal(inst, tour, q, rng)
    return remaining, removed


# ---------------------------------------------------------------------------
# Repair operators: return a complete tour
# ---------------------------------------------------------------------------
def _insertion_costs(inst, tour, c, rng=None, noise=0.0):
    """Cost of inserting `c` at each position of `tour`, cheapest positions first.

    `noise` randomises the ranking. Without it the repair operators are entirely
    deterministic given the remaining tour, so destroy-and-repair regenerates the
    same handful of solutions and the search stalls -- badly so on small
    instances, where a measured 400 rounds produced only four distinct tours.
    The perturbation is the standard ALNS noise term (Ropke & Pisinger 2006):
    each candidate position is offset by `noise * max_distance * U(-1, 1)`.
    """
    d = inst.dist
    n = len(tour)
    amp = 0.0
    if noise > 0.0 and rng is not None:
        finite = d[np.isfinite(d)]
        amp = noise * (float(finite.max()) if finite.size else 0.0)

    # Distance detour alone is the wrong objective here. Because a drone loads
    # its whole route at the depot and sheds weight at each delivery, putting a
    # customer *later* in a route means carrying its parcel across every leg
    # before it. Scoring purely by detour ignores that entirely, and the search
    # then locks onto arrangements that are short but not cheap.
    #
    # So the cost also charges beta * q_c * (distance already flown before pos),
    # which is exactly the extra energy of hauling c's parcel to that point.
    prefix = 0.0
    prefixes = [0.0]
    for i in range(n):
        prev = tour[i - 1] if i > 0 else 0
        prefix += d[prev, tour[i]]
        prefixes.append(prefix)

    q_c = float(inst.demand[c])
    out = []
    for pos in range(n + 1):
        prev = tour[pos - 1] if pos > 0 else 0
        nxt = tour[pos] if pos < n else 0
        detour = d[prev, c] + d[c, nxt] - d[prev, nxt]
        cost = inst.alpha * detour + inst.beta * q_c * prefixes[pos]
        if amp:
            cost += amp * rng.uniform(-1.0, 1.0)
        out.append((cost, pos))
    out.sort()
    return out


def greedy_insert(inst, tour, removed, rng, noise=0.0):
    tour = list(tour)
    pending = list(removed)
    rng.shuffle(pending)
    while pending:
        best = None
        for c in pending:
            cost, pos = _insertion_costs(inst, tour, c, rng, noise)[0]
            if best is None or cost < best[0]:
                best = (cost, pos, c)
        _, pos, c = best
        tour.insert(pos, c)
        pending.remove(c)
    return tour


def _regret_insert(inst, tour, removed, rng, k, noise=0.0):
    tour = list(tour)
    pending = list(removed)
    while pending:
        best = None
        for c in pending:
            costs = _insertion_costs(inst, tour, c, rng, noise)
            best_cost = costs[0][0]
            # how much worse the alternatives are: the regret of postponing c
            regret = sum(costs[min(i, len(costs) - 1)][0] - best_cost
                         for i in range(1, k))
            if best is None or regret > best[0]:
                best = (regret, costs[0][1], c)
        _, pos, c = best
        tour.insert(pos, c)
        pending.remove(c)
    return tour


def regret_2(inst, tour, removed, rng, noise=0.0):
    return _regret_insert(inst, tour, removed, rng, 2, noise)


def regret_3(inst, tour, removed, rng, noise=0.0):
    return _regret_insert(inst, tour, removed, rng, 3, noise)


DESTROY_OPS: List[Tuple[str, Callable]] = [
    ("random", random_removal),
    ("worst", worst_removal),
    ("shaw", shaw_removal),
    ("route", route_removal),
]

REPAIR_OPS: List[Tuple[str, Callable]] = [
    ("greedy", greedy_insert),
    ("regret2", regret_2),
    ("regret3", regret_3),
]


def _select_ops(pool: List[Tuple[str, Callable]],
                names: Optional[Sequence[str]],
                kind: str) -> List[Tuple[str, Callable]]:
    """The named subset of an operator pool, in the pool's own order."""
    if names is None:
        return list(pool)
    known = [name for name, _ in pool]
    unknown = [n for n in names if n not in known]
    if unknown:
        raise ValueError(f"unknown {kind} operator(s) {unknown}; choose from {known}")
    chosen = [op for op in pool if op[0] in set(names)]
    if not chosen:
        raise ValueError(f"at least one {kind} operator is needed")
    return chosen


def _roulette(weights: List[float], rng: random.Random) -> int:
    total = sum(weights)
    if total <= 0:
        return rng.randrange(len(weights))
    r = rng.random() * total
    acc = 0.0
    for i, w in enumerate(weights):
        acc += w
        if r <= acc:
            return i
    return len(weights) - 1


def solve_alns(inst: DRPInstance,
               seed: int = 0,
               max_iter: int = 20000,
               time_limit: float = 30.0,
               warm_tour: Optional[Sequence[int]] = None,
               segment: int = 100,
               reaction: float = 0.35,
               start_temp_factor: float = 0.05,
               cooling: float = 0.9985,
               min_destroy: float = 0.10,
               max_destroy: float = 0.40,
               absolute_max: int = 8,
               noise: float = 0.03,
               destroy_ops: Optional[Sequence[str]] = None,
               repair_ops: Optional[Sequence[str]] = None,
               construct_start: bool = True,
               trace: bool = False,
               trace_max_samples: int = 3000) -> ALNSResult:
    """Run ALNS.

    `reaction` controls how fast operator weights adapt; `noise` randomises the
    repair operators so destroy-and-repair does not keep regenerating the same
    few solutions (see `_insertion_costs`).

    `trace=True` additionally records the search into `ALNSResult.trace` (see
    `drp.meta.trace`): per-step working energy, temperature and which
    destroy/repair pair was drawn, plus -- the point of tracing ALNS at all --
    **one `MetaSegment` per weight update**, carrying the weights as they stood
    after it and the usage and scores that produced them. Only the *final*
    weights were reported before, which shows where the adaptation ended up but
    not that it adapted.

    Opt-in and free when off. For a fixed iteration budget it changes nothing;
    under a wall-clock limit it costs a little time, so fewer iterations fit --
    which is why `bench` and `compare` leave it off.

    `destroy_ops` / `repair_ops` restrict the operator pool to the named
    subset of `DESTROY_OPS` / `REPAIR_OPS` (default: all of them). They exist
    for ablation studies (roadmap §6): the only way to know an operator earns
    its place is to take it away and measure. `construct_start=False` makes a
    run without `warm_tour` start from a random tour instead of building one,
    which is what a cold-start ablation needs.
    """
    destroy_pool = _select_ops(DESTROY_OPS, destroy_ops, "destroy")
    repair_pool = _select_ops(REPAIR_OPS, repair_ops, "repair")
    rng = random.Random(seed)
    t0 = time.time()
    res = ALNSResult()

    def energy_of(tour):
        sol, e = split(inst, tour)
        return e, sol

    if warm_tour:
        cur = list(warm_tour)
    else:
        cur = ((warm_start_tour(inst) if construct_start else None)
               or random_tour(inst, rng))
    cur_e, cur_sol = energy_of(cur)
    tries = 0
    while math.isinf(cur_e) and tries < 200:
        cur = random_tour(inst, rng)
        cur_e, cur_sol = energy_of(cur)
        tries += 1
    if math.isinf(cur_e):
        res.time = time.time() - t0
        return res

    best, best_e, best_sol = cur[:], cur_e, cur_sol
    res.anytime.append((time.time() - t0, best_e))
    T = max(start_temp_factor * best_e, 1e-6)

    nd, nr = len(destroy_pool), len(repair_pool)
    dw, rw = [1.0] * nd, [1.0] * nr
    dscore, rscore = [0.0] * nd, [0.0] * nr
    dused, rused = [0] * nd, [0] * nr

    tr = None
    if trace:
        tr = MetaTracer("alns", max_samples=trace_max_samples,
                        params={"segment": segment, "reaction": reaction,
                                "cooling": cooling, "T0": T, "seed": seed,
                                "time_limit": time_limit,
                                "start_temp_factor": start_temp_factor})
        tr.trace.destroy_ops = [name for name, _ in destroy_pool]
        tr.trace.repair_ops = [name for name, _ in repair_pool]

    # How much to tear down each iteration.
    #
    # Two floors matter, both learned the hard way on small instances. Removing
    # a single customer and reinserting it greedily usually just puts it back,
    # so q = 1 is close to a no-op -- hence a minimum of two. And a percentage
    # ceiling alone is far too tight when n is small (40% of 8 is 3), which left
    # the search regenerating a handful of tours forever; so the ceiling is also
    # allowed to reach `absolute_max`, capped at n - 1.
    n_cust = inst.N - 1
    lo = min(max(2, int(min_destroy * n_cust)), max(2, n_cust - 1))
    hi = max(lo + 1, int(max_destroy * n_cust), min(n_cust - 1, absolute_max))
    hi = min(hi, max(lo + 1, n_cust - 1))

    for it in range(max_iter):
        if time.time() - t0 > time_limit:
            break

        di = _roulette(dw, rng)
        ri = _roulette(rw, rng)
        dused[di] += 1
        rused[ri] += 1

        q = rng.randint(lo, min(hi, max(lo, n_cust - 1)))
        remaining, removed = destroy_pool[di][1](inst, cur, q, rng)
        if not removed:
            continue
        cand = repair_pool[ri][1](inst, remaining, removed, rng, noise)

        ce, csol = energy_of(cand)
        if math.isinf(ce):
            if tr is not None:
                tr.add(MetaSample(step=it, t=time.time() - t0, best=best_e,
                                  current=cur_e, event="infeasible",
                                  temperature=T, accepted=False,
                                  op_destroy=di, op_repair=ri))
            continue

        delta = ce - cur_e
        accepted = delta < 0 or rng.random() < math.exp(-delta / max(T, 1e-9))
        event = "rejected"
        if accepted:
            cur, cur_e, cur_sol = cand, ce, csol
            if cur_e < best_e - 1e-9:
                best, best_e, best_sol = cur[:], cur_e, cur_sol
                res.anytime.append((time.time() - t0, best_e))
                dscore[di] += SCORE_NEW_BEST
                rscore[ri] += SCORE_NEW_BEST
                event = "new_best"
            elif delta < 0:
                dscore[di] += SCORE_IMPROVED
                rscore[ri] += SCORE_IMPROVED
                event = "improved"
            else:
                dscore[di] += SCORE_ACCEPTED
                rscore[ri] += SCORE_ACCEPTED
                event = "accepted"

        if tr is not None:
            now = time.time() - t0
            if event == "new_best":
                tr.event(it, now, "new_best", best_e)
            tr.add(MetaSample(step=it, t=now, best=best_e, current=cur_e,
                              event=event, temperature=T, accepted=accepted,
                              op_destroy=di, op_repair=ri))

        T *= cooling

        if (it + 1) % segment == 0:
            for i in range(nd):
                if dused[i]:
                    dw[i] = (1 - reaction) * dw[i] + reaction * dscore[i] / dused[i]
                    dw[i] = max(dw[i], 0.05)
            for i in range(nr):
                if rused[i]:
                    rw[i] = (1 - reaction) * rw[i] + reaction * rscore[i] / rused[i]
                    rw[i] = max(rw[i], 0.05)
            if tr is not None:
                tr.segment(MetaSegment(step=it, t=time.time() - t0,
                                       destroy_weights=dw[:], repair_weights=rw[:],
                                       destroy_used=dused[:], repair_used=rused[:],
                                       destroy_scores=dscore[:], repair_scores=rscore[:]))
            dscore, rscore = [0.0] * nd, [0.0] * nr
            dused, rused = [0] * nd, [0] * nr

        if it % 50 == 0:
            res.history.append(best_e)
        res.iterations = it + 1

    res.best_solution = best_sol
    res.best_energy = best_e
    res.time = time.time() - t0
    res.destroy_weights = {destroy_pool[i][0]: round(dw[i], 3) for i in range(nd)}
    res.repair_weights = {repair_pool[i][0]: round(rw[i], 3) for i in range(nr)}
    if tr is not None:
        last = (MetaSample(step=res.iterations - 1, t=res.time, best=best_e,
                           current=cur_e, temperature=T)
                if res.iterations > 0 else None)
        res.trace = tr.finish(res.iterations, last)
    return res
