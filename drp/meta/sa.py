"""Simulated Annealing over giant tours.

Local search on the same encoding as the GA, so the two are directly comparable.
SA extends plain descent by accepting a worsening move of size ``delta`` with
probability ``exp(-delta / T)``, which lets it escape the local optima that trap
hill-climbing.

The neighbourhood is compound -- 2-opt reversal, swap, or-move -- drawn at
random each iteration. The initial temperature is calibrated from the average
observed move delta so that early acceptance is about `init_accept`. On
stagnation the search reheats and restarts from the incumbent, which adds
diversification without losing the best solution found.

Cooling is geometric, but the *rate* is re-derived from the clock rather than
fixed
--------------------------------------------------------------------------
A fixed ``gamma`` cools per **iteration** while every run here is bounded by
**time**, so the amount of annealing that actually happens depends on how many
iterations fit in the budget -- on `n`, on `K`, on the machine, and on how fast
`drp.meta.split` happens to be that week. Get few iterations and the schedule
never leaves its random-walk phase: the search accepts almost everything, never
exploits, and returns the incumbent it started from.

That is not hypothetical. On the Solomon sets it made SA return its
Clarke-Wright warm start on *every one* of 56 instances at `n = 25` and `n = 50`
-- 86% of moves accepted, 5,000 iterations, not one improvement -- and it did the
same on two of the twelve Pontianak instances. Both looked like the search being
trapped, and neither was: with the same code and a faster fixed cooling rate SA
improves on all of them.

So `gamma` is now recalibrated every `RECALIBRATE_EVERY` iterations from the
measured iteration rate, to land at `FINAL_TEMP_RATIO` of the starting
temperature exactly when the budget runs out. The parameter remains the value
used until the first recalibration, and for runs given no time limit.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from drp.core.instance import DRPInstance
from drp.core.solution import Solution
from drp.meta.encoding import random_neighbour, random_tour
from drp.meta.split import split
from drp.meta.trace import MetaSample, MetaTrace, MetaTracer


#: How often the cooling rate is re-derived from the clock.
RECALIBRATE_EVERY = 200

#: Where the schedule should land by the end of the budget, relative to T0.
FINAL_TEMP_RATIO = 1e-3


@dataclass
class SAResult:
    best_solution: Optional[Solution] = None
    best_energy: float = math.inf
    history: List[float] = field(default_factory=list)
    iterations: int = 0
    time: float = 0.0
    reheats: int = 0
    accepted: int = 0
    #: ``(seconds, energy)`` at the start and at every new best -- the anytime
    #: curve (roadmap §6). Always on: it is appended only when the best
    #: improves, which is rare, and consumes no random numbers.
    anytime: List[Tuple[float, float]] = field(default_factory=list)
    accepted_uphill: int = 0
    trace: Optional[MetaTrace] = None


def solve_sa(inst: DRPInstance,
             seed: int = 0,
             max_iter: int = 60000,
             gamma: float = 0.9995,
             init_accept: float = 0.8,
             reheat_after: int = 4000,
             time_limit: float = 30.0,
             warm_tour: Optional[Sequence[int]] = None,
             trace: bool = False,
             trace_max_samples: int = 3000) -> SAResult:
    """Run simulated annealing.

    `trace=True` additionally records the search into `SAResult.trace` (see
    `drp.meta.trace`): the working energy, the best-so-far and the temperature
    over both iteration index and wall-clock seconds, with reheats marked. It is
    opt-in and costs nothing when off.

    On the invariance claim, precisely: **for a fixed iteration budget the trace
    changes nothing** -- same solution, energy, history, acceptance counts and
    reheats, because it consumes no random numbers and takes no branches the
    search can see. Under a *wall-clock* limit it does cost a little time, so
    fewer iterations fit inside the budget and the answer may differ, exactly as
    any other overhead would. That is why `bench` and `compare` leave it off.
    """
    rng = random.Random(seed)
    t0 = time.time()
    res = SAResult()

    def energy_of(tour: Sequence[int]):
        sol, e = split(inst, tour)
        return e, sol

    cur = list(warm_tour) if warm_tour else random_tour(inst, rng)
    cur_e, cur_sol = energy_of(cur)
    tries = 0
    while math.isinf(cur_e) and tries < 200:
        cur = random_tour(inst, rng)
        cur_e, cur_sol = energy_of(cur)
        tries += 1

    best, best_e, best_sol = cur[:], cur_e, cur_sol
    if math.isfinite(best_e):
        res.anytime.append((time.time() - t0, best_e))

    # Calibrate the starting temperature so that early acceptance ~ init_accept.
    deltas = []
    for _ in range(60):
        ce, _ = energy_of(random_neighbour(cur, rng))
        if not math.isinf(ce):
            deltas.append(abs(ce - cur_e))
    avg_delta = (sum(deltas) / len(deltas)) if deltas else 1.0
    T = T0 = -avg_delta / math.log(init_accept) if avg_delta > 0 else 1.0

    tr = None
    if trace:
        tr = MetaTracer("sa", max_samples=trace_max_samples,
                        params={"gamma": gamma, "init_accept": init_accept,
                                "reheat_after": reheat_after, "T0": T0,
                                "seed": seed, "time_limit": time_limit})

    def cooling_rate(temperature: float, elapsed: float, done: int) -> float:
        """The gamma that lands at `FINAL_TEMP_RATIO * T0` when time runs out.

        Estimated from the rate achieved so far, so a slow instance cools per
        iteration faster than a quick one and both finish annealed.
        """
        if not math.isfinite(time_limit) or done <= 0 or elapsed <= 0:
            return gamma
        remaining_s = time_limit - elapsed
        if remaining_s <= 0:
            return gamma
        expected = min(remaining_s * (done / elapsed), max_iter - done)
        if expected < 1:
            return gamma
        target = max(T0 * FINAL_TEMP_RATIO, 1e-12)
        if temperature <= target:
            return 1.0                       # already cold; hold it there
        return (target / temperature) ** (1.0 / expected)

    stagnation = 0
    it = 0
    gamma_now = gamma
    for it in range(max_iter):
        now = time.time()
        if now - t0 > time_limit:
            break
        if it % RECALIBRATE_EVERY == 0:
            gamma_now = cooling_rate(T, now - t0, it)
        cand = random_neighbour(cur, rng)
        ce, csol = energy_of(cand)
        if math.isinf(ce):
            if tr is not None:
                tr.add(MetaSample(step=it, t=time.time() - t0, best=best_e,
                                  current=cur_e, event="infeasible",
                                  temperature=T, accepted=False))
            continue
        delta = ce - cur_e
        event = "rejected"
        took = False
        if delta < 0 or rng.random() < math.exp(-delta / max(T, 1e-9)):
            took = True
            cur, cur_e, cur_sol = cand, ce, csol
            res.accepted += 1
            if delta > 0:
                res.accepted_uphill += 1
            if cur_e < best_e - 1e-9:
                best, best_e, best_sol = cur[:], cur_e, cur_sol
                stagnation = 0
                event = "new_best"
                res.anytime.append((time.time() - t0, best_e))
            else:
                stagnation += 1
                event = "improved" if delta < 0 else "accepted"
        else:
            stagnation += 1

        if tr is not None:
            sampled_at = time.time() - t0
            if event == "new_best":
                tr.event(it, sampled_at, "new_best", best_e)
            tr.add(MetaSample(step=it, t=sampled_at, best=best_e, current=cur_e,
                              event=event, temperature=T, accepted=took))

        T *= gamma_now
        if stagnation >= reheat_after:
            T = T0 * 0.5
            stagnation = 0
            res.reheats += 1
            cur, cur_e, cur_sol = best[:], best_e, best_sol
            if tr is not None:
                tr.event(it, time.time() - t0, "reheat", T)
            gamma_now = cooling_rate(T, time.time() - t0, it + 1)

        if it % 200 == 0:
            res.history.append(best_e)
        res.iterations = it + 1

    res.best_solution = best_sol
    res.best_energy = best_e
    res.time = time.time() - t0
    if tr is not None:
        last = (MetaSample(step=res.iterations - 1, t=res.time, best=best_e,
                           current=cur_e, temperature=T)
                if res.iterations > 0 else None)
        res.trace = tr.finish(res.iterations, last)
    return res
