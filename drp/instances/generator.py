"""Reproducible instance generation.

Two families:

  * `generate_instance` -- the original synthetic generator, kept byte-for-byte
    compatible with the graded notebook so `default_benchmark_suite()` still
    reproduces the committed results exactly.
  * `generate_zone_instance` -- the same, but with polygonal no-fly zones
    (roadmap §4.1) instead of the coarse forbidden-edge proxy.

Sizing rationale
----------------
Payload is a slack multiple of the minimum feasible per-drone capacity, so the
fleet can carry all demand but a drone can take several customers rather than
exactly its share -- that keeps the partitioning decision non-trivial. The
battery is calibrated against a nearest-neighbour tour cost divided across the
fleet, so feasible partitions exist while loose routes genuinely risk exceeding
it, rather than the constraint being vacuous.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

import numpy as np

from drp.core.instance import DRPInstance
from drp.geometry.nofly import Polygon, circle_polygon, point_in_any


def _nn_route_cost_estimate(inst: DRPInstance) -> float:
    """Cheap nearest-neighbour single-tour cost, used to calibrate the battery."""
    d = inst.dist
    unvisited = set(range(1, inst.N))
    cur = 0
    cost = 0.0
    onboard = inst.demand[1:].sum()
    while unvisited:
        nxt = min(unvisited, key=lambda j: d[cur, j])
        cost += d[cur, nxt] * (inst.alpha + inst.beta * onboard)
        onboard -= inst.demand[nxt]
        cur = nxt
        unvisited.discard(nxt)
    cost += d[cur, 0] * inst.alpha
    return cost


def generate_instance(name: str,
                      n_customers: int,
                      n_drones: int,
                      seed: int,
                      area: float = 100.0,
                      d_min: float = 1.0,
                      d_max: float = 5.0,
                      alpha: float = 1.0,
                      beta: float = 0.3,
                      payload_factor: float = 1.7,
                      battery_factor: float = 0.9,
                      nofly_fraction: float = 0.0) -> DRPInstance:
    """Synthetic instance. `nofly_fraction` forbids that share of longest edges.

    This reproduces the graded notebook's generator exactly; do not change the
    sampling order without also re-running the experimental study.
    """
    rng = np.random.default_rng(seed)
    coords = rng.uniform(0, area, size=(n_customers + 1, 2))
    coords[0] = [area / 2, area / 2]
    demand = np.zeros(n_customers + 1)
    demand[1:] = rng.uniform(d_min, d_max, size=n_customers)

    total_demand = demand.sum()
    min_required = total_demand / n_drones
    payload = max(d_max, payload_factor * min_required)
    payload = max(payload, demand.max())

    inst = DRPInstance(
        name=name, n_customers=n_customers, n_drones=n_drones,
        coords=coords, demand=demand, battery=math.inf, payload=payload,
        alpha=alpha, beta=beta, seed=seed,
    )

    if nofly_fraction > 0:
        d = inst.dist
        edges = [(i, j, d[i, j]) for i in range(1, inst.N)
                 for j in range(i + 1, inst.N)]
        edges.sort(key=lambda x: -x[2])
        k = int(nofly_fraction * len(edges))
        inst.nofly_edges = set((e[0], e[1]) for e in edges[:k])

    nn = _nn_route_cost_estimate(inst)
    per_drone = nn / max(1, inst.n_drones - 1) if inst.n_drones > 1 else nn
    inst.battery = battery_factor * max(nn / inst.n_drones, per_drone)
    return inst


def generate_zone_instance(name: str,
                           n_customers: int,
                           n_drones: int,
                           seed: int,
                           n_zones: int = 3,
                           zone_radius: float = 12.0,
                           area: float = 100.0,
                           d_min: float = 1.0,
                           d_max: float = 5.0,
                           alpha: float = 1.0,
                           beta: float = 0.3,
                           payload_factor: float = 1.7,
                           battery_factor: float = 1.1) -> DRPInstance:
    """Instance with polygonal no-fly zones and detour-aware distances.

    Zones are placed away from the depot, and customers are rejected and
    resampled if they land inside one, so every instance stays solvable.
    """
    rng = np.random.default_rng(seed)
    depot = np.array([area / 2, area / 2])

    zones: List[Polygon] = []
    centres: List[Tuple[float, float]] = []
    attempts = 0
    while len(zones) < n_zones and attempts < 500:
        attempts += 1
        cx, cy = rng.uniform(0.15 * area, 0.85 * area, size=2)
        if math.hypot(cx - depot[0], cy - depot[1]) < zone_radius * 1.6:
            continue  # keep the depot clear
        if any(math.hypot(cx - px, cy - py) < 2.2 * zone_radius
               for px, py in centres):
            continue  # keep zones disjoint
        centres.append((cx, cy))
        zones.append(circle_polygon(cx, cy, zone_radius, sides=8))

    coords = np.zeros((n_customers + 1, 2))
    coords[0] = depot
    placed = 0
    while placed < n_customers:
        p = rng.uniform(0, area, size=2)
        if point_in_any((p[0], p[1]), zones):
            continue
        placed += 1
        coords[placed] = p

    demand = np.zeros(n_customers + 1)
    demand[1:] = rng.uniform(d_min, d_max, size=n_customers)

    payload = max(d_max, payload_factor * demand.sum() / n_drones, demand.max())

    inst = DRPInstance(
        name=name, n_customers=n_customers, n_drones=n_drones,
        coords=coords, demand=demand, battery=math.inf, payload=payload,
        alpha=alpha, beta=beta, nofly_zones=zones, seed=seed,
    )
    nn = _nn_route_cost_estimate(inst)
    per_drone = nn / max(1, inst.n_drones - 1) if inst.n_drones > 1 else nn
    inst.battery = battery_factor * max(nn / inst.n_drones, per_drone)
    return inst


BENCHMARK_SPECS: Sequence[Tuple[str, int, int, int, float]] = [
    ("S1_n5_k2", 5, 2, 101, 0.0),
    ("S2_n6_k2", 6, 2, 102, 0.0),
    ("S3_n7_k2", 7, 3, 103, 0.0),
    ("S4_n8_k3", 8, 3, 104, 0.10),
    ("S5_n9_k3", 9, 3, 105, 0.0),
    ("S6_n10_k3", 10, 3, 106, 0.10),
    ("M1_n12_k4", 12, 4, 107, 0.0),
    ("M2_n15_k4", 15, 4, 108, 0.10),
    ("M3_n18_k5", 18, 5, 109, 0.0),
    ("L1_n20_k5", 20, 5, 110, 0.10),
    ("L2_n25_k6", 25, 6, 111, 0.0),
    ("L3_n30_k6", 30, 6, 112, 0.10),
]


def default_benchmark_suite() -> List[DRPInstance]:
    """The 12 instances behind the report. Sizes span the range where Branch &
    Bound is tractable through to where only metaheuristics remain useful."""
    return [generate_instance(name, n, k, seed, nofly_fraction=nf)
            for name, n, k, seed, nf in BENCHMARK_SPECS]


def zone_benchmark_suite(n_instances: int = 6) -> List[DRPInstance]:
    """A companion suite exercising polygonal zones and detour routing."""
    specs = [(8, 3), (10, 3), (12, 4), (15, 4), (18, 5), (20, 5)]
    return [generate_zone_instance(f"Z{i+1}_n{n}_k{k}", n, k, 200 + i)
            for i, (n, k) in enumerate(specs[:n_instances])]
