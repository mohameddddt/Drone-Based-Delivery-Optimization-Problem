"""Giant-tour encoding: the permutation operators shared by GA, SA and ALNS.

Keeping the operators here means the three metaheuristics genuinely share a
neighbourhood definition, so differences between them are differences of search
strategy rather than of move repertoire.
"""
from __future__ import annotations

import random
from typing import List, Optional, Sequence

from drp.core.instance import DRPInstance


def random_tour(inst: DRPInstance, rng: random.Random) -> List[int]:
    tour = list(range(1, inst.N))
    rng.shuffle(tour)
    return tour


def order_crossover(p1: Sequence[int], p2: Sequence[int],
                    rng: random.Random) -> List[int]:
    """Order Crossover (OX): keep a slice of p1, fill from p2 in p2's order.

    Preserves relative order, which is what matters for a routing permutation,
    and always produces a valid permutation.
    """
    n = len(p1)
    a, b = sorted(rng.sample(range(n), 2))
    child: List[Optional[int]] = [None] * n
    child[a:b + 1] = list(p1[a:b + 1])
    taken = set(p1[a:b + 1])
    fill = [g for g in p2 if g not in taken]
    idx = 0
    for i in range(n):
        if child[i] is None:
            child[i] = fill[idx]
            idx += 1
    return [int(c) for c in child]


def swap_mutation(tour: List[int], rng: random.Random) -> None:
    """Exchange two positions. In place."""
    if len(tour) < 2:
        return
    i, j = rng.sample(range(len(tour)), 2)
    tour[i], tour[j] = tour[j], tour[i]


def reverse_mutation(tour: List[int], rng: random.Random) -> None:
    """2-opt style: reverse a random segment. In place."""
    if len(tour) < 2:
        return
    i, j = sorted(rng.sample(range(len(tour)), 2))
    tour[i:j + 1] = reversed(tour[i:j + 1])


def or_move(tour: List[int], rng: random.Random) -> None:
    """Relocate one customer elsewhere in the tour. In place."""
    n = len(tour)
    if n < 2:
        return
    i = rng.randrange(n)
    c = tour.pop(i)
    tour.insert(rng.randrange(len(tour) + 1), c)


def random_neighbour(tour: Sequence[int], rng: random.Random) -> List[int]:
    """One random move from the compound neighbourhood: swap, 2-opt, or-move."""
    t = list(tour)
    r = rng.random()
    if r < 0.34:
        swap_mutation(t, rng)
    elif r < 0.67:
        reverse_mutation(t, rng)
    else:
        or_move(t, rng)
    return t
