from __future__ import annotations

import random
from math import exp, inf, isfinite
from time import perf_counter

from .models import Instance, Solution
from .routing import nearest_neighbor_permutation, split_permutation


def solve_simulated_annealing(
    instance: Instance,
    seed: int = 0,
    iterations: int = 9000,
    initial_temperature: float | None = None,
    final_temperature: float = 0.01,
) -> Solution:
    started = perf_counter()
    rng = random.Random(seed)
    current = nearest_neighbor_permutation(instance)
    current_cost = _cost(instance, current)
    if not isfinite(current_cost):
        nodes = list(instance.customer_nodes)
        for _ in range(200):
            rng.shuffle(nodes)
            candidate = tuple(nodes)
            value = _cost(instance, candidate)
            if value < current_cost:
                current = candidate
                current_cost = value
            if isfinite(current_cost):
                break

    best = current
    best_cost = current_cost
    temperature = initial_temperature or max(1.0, best_cost * 0.08 if isfinite(best_cost) else 10.0)
    cooling = (final_temperature / temperature) ** (1.0 / max(1, iterations))
    completed = 0

    for iteration in range(iterations):
        candidate = neighbor(current, rng)
        candidate_cost = _cost(instance, candidate)
        accept = candidate_cost < current_cost
        if not accept and isfinite(candidate_cost):
            difference = candidate_cost - current_cost
            if not isfinite(current_cost):
                accept = True
            else:
                accept = rng.random() < exp(-difference / max(temperature, 1e-12))
        if accept:
            current = candidate
            current_cost = candidate_cost
            if current_cost < best_cost:
                best = current
                best_cost = current_cost
        temperature *= cooling
        completed = iteration + 1

    solution = split_permutation(instance, best, method="Simulated Annealing")
    solution.runtime_sec = perf_counter() - started
    solution.iterations = completed
    return solution


def neighbor(permutation: tuple[int, ...], rng: random.Random) -> tuple[int, ...]:
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


def _cost(instance: Instance, permutation: tuple[int, ...]) -> float:
    solution = split_permutation(instance, permutation)
    return solution.cost if solution.feasible else inf
