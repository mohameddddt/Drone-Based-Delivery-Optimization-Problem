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
from typing import List, Optional, Sequence

from drp.core.instance import DRPInstance
from drp.core.solution import Solution
from drp.meta.encoding import (order_crossover, random_tour, reverse_mutation,
                               swap_mutation)
from drp.meta.split import split


@dataclass
class GAResult:
    best_solution: Optional[Solution] = None
    best_energy: float = math.inf
    history: List[float] = field(default_factory=list)
    generations: int = 0
    time: float = 0.0


def solve_ga(inst: DRPInstance,
             pop_size: int = 60,
             generations: int = 400,
             crossover_rate: float = 0.9,
             mutation_rate: float = 0.3,
             elite: int = 4,
             seed: int = 0,
             time_limit: float = 30.0,
             warm_tours: Optional[Sequence[Sequence[int]]] = None) -> GAResult:
    rng = random.Random(seed)
    t0 = time.time()
    res = GAResult()

    def fitness(tour: Sequence[int]) -> float:
        return split(inst, tour)[1]

    population: List[List[int]] = [list(t) for t in (warm_tours or [])]
    while len(population) < pop_size:
        population.append(random_tour(inst, rng))

    scored = sorted(((fitness(t), t) for t in population), key=lambda x: x[0])

    def tournament() -> List[int]:
        i, j = rng.randrange(len(scored)), rng.randrange(len(scored))
        return scored[i][1] if scored[i][0] <= scored[j][0] else scored[j][1]

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

    best_tour = scored[0][1]
    sol, e = split(inst, best_tour)
    res.best_solution = sol
    res.best_energy = e
    res.time = time.time() - t0
    return res
