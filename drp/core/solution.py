"""The solution representation.

A solution is a list of routes. Each route is a list of customer indices with
the depot implicit at both ends, so ``[[3, 1], [2], []]`` means drone 1 flies
0-3-1-0, drone 2 flies 0-2-0, and drone 3 is unused.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, List


@dataclass
class Solution:
    routes: List[List[int]]

    def copy(self) -> "Solution":
        return Solution([r[:] for r in self.routes])

    def used_routes(self) -> List[List[int]]:
        """The non-empty routes, i.e. the drones that actually fly."""
        return [r for r in self.routes if r]

    def customers(self) -> List[int]:
        """Every customer visited, in route order. Duplicates are kept so that
        feasibility checking can detect them."""
        return [c for r in self.routes for c in r]

    def giant_tour(self) -> List[int]:
        """Flatten to a delimiter-free permutation, the metaheuristic encoding."""
        return self.customers()

    def __iter__(self) -> Iterator[List[int]]:
        return iter(self.routes)

    def __len__(self) -> int:
        return len(self.routes)
