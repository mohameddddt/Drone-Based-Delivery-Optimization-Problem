from __future__ import annotations

import random
from math import ceil, cos, pi, sin, sqrt
from pathlib import Path

from .geometry import euclidean
from .io import save_instance
from .models import Customer, DroneLimits, EnergyModel, Instance


def build_instance(name: str, n_customers: int, seed: int) -> Instance:
    rng = random.Random(seed)
    depot = (0.0, 0.0)
    customers: list[Customer] = []
    for index in range(1, n_customers + 1):
        angle = rng.random() * 2.0 * pi
        radius = sqrt(rng.random()) * 4.2
        x = cos(angle) * radius
        y = sin(angle) * radius
        demand = round(rng.uniform(1.2, 2.2), 3)
        customers.append(Customer(index, f"C{index:03d}", x, y, demand))

    points = [depot] + [(customer.x, customer.y) for customer in customers]
    distance = [[euclidean(a, b) for b in points] for a in points]
    max_payload = 5.0
    total_demand = sum(customer.demand for customer in customers)
    n_drones = max(3, ceil(total_demand / max_payload) + 1)
    size = n_customers + 1
    allowed = [[i != j for j in range(size)] for i in range(size)]
    return Instance(
        name=name,
        customers=customers,
        depot=depot,
        distance=distance,
        allowed=allowed,
        n_drones=n_drones,
        limits=DroneLimits(max_payload=max_payload, max_battery_km=18.0),
        energy=EnergyModel(energy_per_km=1.0, payload_factor=0.18),
        no_fly_zones=[],
        seed=seed,
    )


def generate_benchmark(output: str | Path, count: int = 10, seed: int = 2026) -> list[Path]:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index in range(1, count + 1):
        n_customers = 7 + index
        instance_seed = seed + index * 97
        instance = build_instance(f"instance_{index:02d}", n_customers, instance_seed)
        folder = output / instance.name
        save_instance(instance, folder)
        paths.append(folder)
    return paths
