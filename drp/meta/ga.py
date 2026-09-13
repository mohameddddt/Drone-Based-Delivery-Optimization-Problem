"""Genetic Algorithm over giant tours.

Population-based search on the permutation encoding, decoded by Split. Binary
tournament selection, Order Crossover, swap and 2-opt mutation, and elitism so
the best individuals always survive. A chromosome Split cannot fit into K drones
scores infinity and dies out.

Roadmap §5.2 notes the obvious upgrade: adding local search inside the loop to
make this a proper memetic algorithm.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from drp.core.instance import DRPInstance
from drp.core.solution import Solution
from drp.meta.encoding import (order_crossover, random_tour, reverse_mutation,
                               swap_mutation)
from drp.meta.split import split
from drp.meta.trace import MetaSample, MetaTrace, MetaTracer


@dataclass
class GAResult:
    best_solution: Optional[Solution] = None
    best_energy: float = math.inf
    history: List[float] = field(default_factory=list)
    generations: int = 0
    time: float = 0.0
    #: ``(seconds, energy)`` at the start and whenever the best improves --
    #: the anytime curve (roadmap §6).
    anytime: List[Tuple[float, float]] = field(default_factory=list)
    trace: Optional[MetaTrace] = None


def solve_ga(inst: DRPInstance,
             pop_size: int = 60,
             generations: int = 400,
             crossover_rate: float = 0.9,
             mutation_rate: float = 0.3,
             elite: int = 4,
             seed: int = 0,
             time_limit: float = 30.0,
             warm_tours: Optional[Sequence[Sequence[int]]] = None,
             trace: bool = False,
             trace_max_samples: int = 3000) -> GAResult:
    """Run the GA.

    `trace=True` additionally records the search into `GAResult.trace` (see
    `drp.meta.trace`). A GA is a *population*, and a best-of-generation line
    says nothing about whether that population converged or collapsed -- so each
    sample also carries the population's mean energy and its spread (worst minus
    best, over the feasible members). Watching the spread close on the best is
    watching the GA lose diversity.

    Opt-in and free when off. For a fixed generation budget it changes nothing;
    under a wall-clock limit it costs a little time, so fewer generations fit --
    which is why `bench` and `compare` leave it off.
    """
    rng = random.Random(seed)
    t0 = time.time()
    res = GAResult()

    def fitness(tour: Sequence[int]) -> float:
        return split(inst, tour)[1]

    population: List[List[int]] = [list(t) for t in (warm_tours or [])]
    while len(population) < pop_size:
        population.append(random_tour(inst, rng))

    scored = sorted(((fitness(t), t) for t in population), key=lambda x: x[0])

    tr = None
    if trace:
        tr = MetaTracer("ga", max_samples=trace_max_samples,
                        params={"pop_size": pop_size, "elite": elite,
                                "crossover_rate": crossover_rate,
                                "mutation_rate": mutation_rate, "seed": seed,
                                "time_limit": time_limit})

    def population_stats(pop):
        """Mean and spread over the *feasible* members.

        Split returns inf for a tour no drone assignment can serve, and an inf
        in the mean would swallow the whole series -- so infeasible members are
        counted (`n_feasible`) rather than averaged in.
        """
        vals = [e for e, _ in pop if math.isfinite(e)]
        if not vals:
            return None, None, 0
        return sum(vals) / len(vals), max(vals) - min(vals), len(vals)

    def tournament() -> List[int]:
        i, j = rng.randrange(len(scored)), rng.randrange(len(scored))
        return scored[i][1] if scored[i][0] <= scored[j][0] else scored[j][1]

    best_seen = [scored[0][0] if scored else math.inf]
    anytime_best = best_seen[0]
    if math.isfinite(anytime_best):
        res.anytime.append((time.time() - t0, anytime_best))
    gen = 0
    for gen in range(generations):
        if time.time() - t0 > time_limit:
            break
        new_pop: List[List[int]] = [scored[k][1][:] for k in range(min(elite, len(scored)))]
        while len(new_pop) < pop_size:
            p1 = tournament()
            if rng.random() < crossover_rate:
                child = order_crossover(p1, tournament(), rng)
            else:
                child = p1[:]
            if rng.random() < mutation_rate:
                (swap_mutation if rng.random() < 0.5 else reverse_mutation)(child, rng)
            new_pop.append(child)
        scored = sorted(((fitness(t), t) for t in new_pop), key=lambda x: x[0])
        res.history.append(scored[0][0])
        res.generations = gen + 1
        if scored[0][0] < anytime_best - 1e-9:
            anytime_best = scored[0][0]
            res.anytime.append((time.time() - t0, anytime_best))

        if tr is not None:
            now = time.time() - t0
            gen_best = scored[0][0]
            mean, spread, n_feas = population_stats(scored)
            if gen_best < best_seen[0] - 1e-9:
                best_seen[0] = gen_best
                tr.event(gen, now, "new_best", gen_best)
            tr.add(MetaSample(step=gen, t=now, best=best_seen[0],
                              current=gen_best, event="generation",
                              mean=mean, spread=spread))
            tr.trace.params["n_feasible_last"] = n_feas

    best_tour = scored[0][1]
    sol, e = split(inst, best_tour)
    res.best_solution = sol
    res.best_energy = e
    res.time = time.time() - t0
    if tr is not None:
        mean, spread, _ = population_stats(scored)
        last = (MetaSample(step=res.generations - 1, t=res.time, best=e,
                           current=scored[0][0], event="generation",
                           mean=mean, spread=spread)
                if res.generations > 0 else None)
        res.trace = tr.finish(res.generations, last)
    return res
