from __future__ import annotations

import random
from math import inf
from time import perf_counter

from .models import Instance, Solution
from .routing import nearest_neighbor_permutation, split_permutation


def solve_genetic(
    instance: Instance,
    seed: int = 0,
    population_size: int = 70,
    generations: int = 220,
    mutation_rate: float = 0.25,
    elite_size: int = 4,
) -> Solution:
    started = perf_counter()
    rng = random.Random(seed)
    nodes = list(instance.customer_nodes)
    population: list[tuple[int, ...]] = [nearest_neighbor_permutation(instance)]
    while len(population) < population_size:
        candidate = nodes[:]
        rng.shuffle(candidate)
        population.append(tuple(candidate))

    cache: dict[tuple[int, ...], float] = {}

    def fitness(permutation: tuple[int, ...]) -> float:
        value = cache.get(permutation)
        if value is not None:
            return value
        solution = split_permutation(instance, permutation, method="Genetic Algorithm")
        value = solution.cost if solution.feasible else inf
        cache[permutation] = value
        return value

    def tournament(scored: list[tuple[float, tuple[int, ...]]]) -> tuple[int, ...]:
        sample = rng.sample(scored, k=min(4, len(scored)))
        return min(sample, key=lambda item: item[0])[1]

    best_permutation = population[0]
    best_cost = fitness(best_permutation)
    completed = 0

    for generation in range(generations):
        scored = sorted((fitness(permutation), permutation) for permutation in population)
        if scored[0][0] < best_cost:
            best_cost, best_permutation = scored[0]
        next_population = [permutation for _, permutation in scored[:elite_size]]
        while len(next_population) < population_size:
            first = tournament(scored)
            second = tournament(scored)
            child = ordered_crossover(first, second, rng)
            if rng.random() < mutation_rate:
                child = mutate(child, rng)
            next_population.append(child)
        population = next_population
        completed = generation + 1

    solution = split_permutation(instance, best_permutation, method="Genetic Algorithm")
    solution.runtime_sec = perf_counter() - started
    solution.iterations = completed
    return solution


def ordered_crossover(
    first: tuple[int, ...],
    second: tuple[int, ...],
    rng: random.Random,
) -> tuple[int, ...]:
    n = len(first)
    left, right = sorted(rng.sample(range(n), 2))
    child: list[int | None] = [None] * n
    child[left : right + 1] = first[left : right + 1]
    used = set(first[left : right + 1])
    position = (right + 1) % n
    for gene in second:
        if gene in used:
            continue
        child[position] = gene
        position = (position + 1) % n
    return tuple(gene for gene in child if gene is not None)


def mutate(permutation: tuple[int, ...], rng: random.Random) -> tuple[int, ...]:
    values = list(permutation)
    move = rng.choice(["swap", "reverse", "insert"])
    i, j = sorted(rng.sample(range(len(values)), 2))
    if move == "swap":
        values[i], values[j] = values[j], values[i]
    elif move == "reverse":
        values[i : j + 1] = reversed(values[i : j + 1])
    else:
        gene = values.pop(j)
        values.insert(i, gene)
    return tuple(values)
