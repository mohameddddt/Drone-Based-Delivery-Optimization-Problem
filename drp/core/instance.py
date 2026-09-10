"""The problem instance.

`DRPInstance` is the single description of a Drone Routing Problem: where the
customers are, what they weigh, how many drones there are, and what the drones
can do. Everything else in the package reads it and does not mutate it.

The distance matrix is the extension point. By default it is Euclidean, but if
the instance carries polygonal no-fly zones the matrix becomes the
*obstacle-avoiding* shortest path between each pair (see
`drp.geometry.visibility`). Solvers never learn about zones: they see a distance
matrix that already routes around them.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Set, Tuple

import numpy as np

EPS = 1e-9


@dataclass
class DRPInstance:
    """An instance of the Drone Routing Problem.

    Node 0 is the depot; nodes 1..n_customers are customers.

    Attributes
    ----------
    coords
        Shape ``(n_customers + 1, 2)``; row 0 is the depot.
    demand
        Shape ``(n_customers + 1,)``; ``demand[0]`` is 0.
    battery
        Maximum energy one drone may spend on its route.
    payload
        Maximum weight one drone may carry.
    alpha, beta
        Energy model coefficients: traversing distance ``d`` carrying weight
        ``w`` costs ``d * (alpha + beta * w)``.
    nofly_edges
        Forbidden node pairs, stored undirected as ``(min, max)``. This is the
        original coarse no-fly representation.
    nofly_zones
        Polygonal no-fly zones, each a sequence of ``(x, y)`` vertices. When
        present the distance matrix routes around them instead of forbidding
        edges outright.
    geodesic
        If True, coordinates are ``(lat, lon)`` and distances are haversine
        kilometres rather than Euclidean units.
    round_distances
        If True, every distance is rounded to the nearest integer. This exists
        for imported CVRPLIB/TSPLIB instances, whose published optima are
        defined on the rounded ``EUC_2D`` metric -- without it a comparison
        against a best-known value is comparing two different problems
        (roadmap §3.3).
    """

    name: str
    n_customers: int
    n_drones: int
    coords: np.ndarray
    demand: np.ndarray
    battery: float
    payload: float
    alpha: float = 1.0
    beta: float = 0.3
    nofly_edges: Set[Tuple[int, int]] = field(default_factory=set)
    nofly_zones: List[Sequence[Tuple[float, float]]] = field(default_factory=list)
    geodesic: bool = False
    round_distances: bool = False
    seed: Optional[int] = None

    _dist: Optional[np.ndarray] = field(default=None, repr=False, compare=False)

    # -- geometry ----------------------------------------------------------
    @property
    def N(self) -> int:
        """Total node count, including the depot."""
        return self.n_customers + 1

    @property
    def dist(self) -> np.ndarray:
        """Distance matrix, computed once and cached.

        Euclidean or haversine, and detoured around `nofly_zones` if any exist.
        """
        if self._dist is None:
            from drp.geometry.distance import distance_matrix

            base = distance_matrix(self.coords, geodesic=self.geodesic)
            if self.nofly_zones:
                from drp.geometry.visibility import obstacle_distance_matrix

                base = obstacle_distance_matrix(self.coords, self.nofly_zones,
                                                geodesic=self.geodesic)
            if self.round_distances:
                # Rounded after any detour: the detour is part of the distance.
                base = np.rint(base)
            self._dist = base
        return self._dist

    def invalidate_distances(self) -> None:
        """Drop the cached matrix after changing coordinates or zones."""
        self._dist = None

    def edge_forbidden(self, i: int, j: int) -> bool:
        """True if the arc between `i` and `j` may not be flown at all.

        Polygonal zones do *not* forbid arcs -- they lengthen them -- so only
        the explicit `nofly_edges` set is consulted here. An arc whose detour is
        impossible shows up as an infinite distance instead.
        """
        a, b = (i, j) if i < j else (j, i)
        if (a, b) in self.nofly_edges:
            return True
        return math.isinf(self.dist[i, j])

    def total_demand(self) -> float:
        return float(self.demand[1:].sum())
