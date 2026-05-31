from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .geometry import euclidean, segment_intersects_circle
from .models import Customer, DroneLimits, EnergyModel, Instance, Solution


def load_instance(folder: str | Path) -> Instance:
    folder = Path(folder)
    with (folder / "meta.json").open(encoding="utf-8") as file:
        meta = json.load(file)

    customers: list[Customer] = []
    with (folder / "customers.csv").open(newline="", encoding="utf-8") as file:
        for index, row in enumerate(csv.DictReader(file), start=1):
            customer_id = row.get("customer_id") or f"C{index:03d}"
            x = float(row.get("x_km", row.get("x", row.get("lon", 0.0))))
            y = float(row.get("y_km", row.get("y", row.get("lat", 0.0))))
            customers.append(Customer(index, customer_id, x, y, float(row["demand"])))

    depot_data = meta.get("depot", {})
    depot = (
        float(depot_data.get("x_km", depot_data.get("x", 0.0))),
        float(depot_data.get("y_km", depot_data.get("y", 0.0))),
    )

    distance_path = folder / "distance_km.csv"
    if distance_path.exists():
        distance = _read_distance_matrix(distance_path)
    else:
        points = [depot] + [(customer.x, customer.y) for customer in customers]
        distance = [[euclidean(a, b) for b in points] for a in points]

    limits_data = meta.get("limits", {})
    energy_data = meta.get("energy_model", {})
    no_fly_zones = list(meta.get("no_fly_zones", []))
    allowed = _build_allowed(depot, customers, no_fly_zones)
    forbidden_path = folder / "forbidden_edges.csv"
    if forbidden_path.exists():
        _load_forbidden_edges(forbidden_path, allowed)

    return Instance(
        name=meta.get("name", folder.name),
        customers=customers,
        depot=depot,
        distance=distance,
        allowed=allowed,
        n_drones=int(meta.get("n_drones", meta.get("fleet_size", 1))),
        limits=DroneLimits(
            max_payload=float(limits_data.get("max_payload", meta.get("max_payload", 5.0))),
            max_battery_km=float(limits_data.get("max_battery_km", meta.get("max_battery_km", 20.0))),
        ),
        energy=EnergyModel(
            energy_per_km=float(energy_data.get("energy_per_km", meta.get("energy_per_km", 1.0))),
            payload_factor=float(energy_data.get("payload_factor", meta.get("payload_factor", 0.2))),
        ),
        no_fly_zones=no_fly_zones,
        seed=meta.get("seed"),
    )


def save_instance(instance: Instance, folder: str | Path) -> None:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "customers.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["customer_id", "x_km", "y_km", "demand"])
        writer.writeheader()
        for customer in instance.customers:
            writer.writerow(
                {
                    "customer_id": customer.customer_id,
                    "x_km": f"{customer.x:.6f}",
                    "y_km": f"{customer.y:.6f}",
                    "demand": f"{customer.demand:.3f}",
                }
            )

    with (folder / "distance_km.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["node"] + list(range(instance.n_customers + 1)))
        for index, row in enumerate(instance.distance):
            writer.writerow([index] + [f"{value:.6f}" for value in row])

    meta: dict[str, Any] = {
        "name": instance.name,
        "seed": instance.seed,
        "n_customers": instance.n_customers,
        "n_drones": instance.n_drones,
        "depot": {"x_km": instance.depot[0], "y_km": instance.depot[1]},
        "limits": {
            "max_payload": instance.limits.max_payload,
            "max_battery_km": instance.limits.max_battery_km,
        },
        "energy_model": {
            "energy_per_km": instance.energy.energy_per_km,
            "payload_factor": instance.energy.payload_factor,
        },
        "no_fly_zones": instance.no_fly_zones,
    }
    with (folder / "meta.json").open("w", encoding="utf-8") as file:
        json.dump(meta, file, indent=2)


def save_solution(instance: Instance, solution: Solution, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "instance": instance.name,
        "method": solution.method,
        "feasible": solution.feasible,
        "optimal": solution.optimal,
        "cost": solution.cost,
        "distance": solution.total_distance,
        "runtime_sec": solution.runtime_sec,
        "iterations": solution.iterations,
        "lower_bound": solution.lower_bound,
        "gap_percent": solution.gap_percent,
        "routes": [
            {
                "customers": [instance.customer_id(node) for node in route.nodes],
                "load": route.load,
                "distance": route.distance,
                "energy": route.cost,
            }
            for route in solution.routes
        ],
    }
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def _read_distance_matrix(path: Path) -> list[list[float]]:
    with path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.reader(file))
    if not rows:
        return []
    first = rows[0][0].strip().lower()
    if first in {"node", ""}:
        rows = rows[1:]
        return [[float(value) for value in row[1:]] for row in rows]
    return [[float(value) for value in row] for row in rows]


def _build_allowed(
    depot: tuple[float, float],
    customers: list[Customer],
    no_fly_zones: list[dict[str, Any]],
) -> list[list[bool]]:
    points = [depot] + [(customer.x, customer.y) for customer in customers]
    size = len(points)
    allowed = [[i != j for j in range(size)] for i in range(size)]
    for zone in no_fly_zones:
        if zone.get("type") != "circle":
            continue
        center_data = zone.get("center", {})
        if isinstance(center_data, dict):
            center = (float(center_data.get("x_km", 0.0)), float(center_data.get("y_km", 0.0)))
        else:
            center = (float(center_data[0]), float(center_data[1]))
        radius = float(zone.get("radius_km", 0.0))
        for i, start in enumerate(points):
            for j, end in enumerate(points):
                if i != j and segment_intersects_circle(start, end, center, radius):
                    allowed[i][j] = False
    return allowed


def _load_forbidden_edges(path: Path, allowed: list[list[bool]]) -> None:
    with path.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            i = int(row["from"])
            j = int(row["to"])
            if 0 <= i < len(allowed) and 0 <= j < len(allowed):
                allowed[i][j] = False
