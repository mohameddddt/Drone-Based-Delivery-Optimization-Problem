from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Customer:
    index: int
    customer_id: str
    x: float
    y: float
    demand: float


@dataclass(frozen=True)
class DroneLimits:
    max_payload: float
    max_battery_km: float


@dataclass(frozen=True)
class EnergyModel:
    energy_per_km: float
    payload_factor: float


@dataclass
class Instance:
    name: str
    customers: list[Customer]
    depot: tuple[float, float]
    distance: list[list[float]]
    allowed: list[list[bool]]
    n_drones: int
    limits: DroneLimits
    energy: EnergyModel
    no_fly_zones: list[dict[str, Any]] = field(default_factory=list)
    seed: int | None = None

    @property
    def n_customers(self) -> int:
        return len(self.customers)

    @property
    def customer_nodes(self) -> tuple[int, ...]:
        return tuple(range(1, self.n_customers + 1))

    @property
    def full_mask(self) -> int:
        return (1 << self.n_customers) - 1

    @property
    def total_demand(self) -> float:
        return sum(customer.demand for customer in self.customers)

    def demand(self, node: int) -> float:
        if node == 0:
            return 0.0
        return self.customers[node - 1].demand

    def customer_id(self, node: int) -> str:
        if node == 0:
            return "DEPOT"
        return self.customers[node - 1].customer_id

    def point(self, node: int) -> tuple[float, float]:
        if node == 0:
            return self.depot
        customer = self.customers[node - 1]
        return customer.x, customer.y


@dataclass(frozen=True)
class Route:
    nodes: tuple[int, ...]
    cost: float
    distance: float
    load: float
    mask: int

    @property
    def size(self) -> int:
        return len(self.nodes)


@dataclass
class Solution:
    method: str
    routes: list[Route]
    cost: float
    feasible: bool
    runtime_sec: float = 0.0
    iterations: int = 0
    optimal: bool = False
    lower_bound: float | None = None
    gap_percent: float | None = None
    explored_nodes: int = 0

    @property
    def route_count(self) -> int:
        return len(self.routes)

    @property
    def total_distance(self) -> float:
        return sum(route.distance for route in self.routes)
