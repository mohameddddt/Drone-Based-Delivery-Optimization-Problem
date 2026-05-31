from __future__ import annotations

from math import inf, isfinite

from .models import Instance, Route, Solution

EPS = 1e-9


def nodes_to_mask(nodes: tuple[int, ...] | list[int]) -> int:
    mask = 0
    for node in nodes:
        mask |= 1 << (node - 1)
    return mask


def make_route(instance: Instance, nodes: tuple[int, ...] | list[int]) -> Route | None:
    route_nodes = tuple(nodes)
    if not route_nodes:
        return None
    load = sum(instance.demand(node) for node in route_nodes)
    if load > instance.limits.max_payload + EPS:
        return None

    current = 0
    remaining = load
    distance = 0.0
    cost = 0.0
    for node in route_nodes:
        if not instance.allowed[current][node]:
            return None
        leg = instance.distance[current][node]
        if not isfinite(leg):
            return None
        distance += leg
        cost += leg * instance.energy.energy_per_km * (1.0 + instance.energy.payload_factor * remaining)
        remaining -= instance.demand(node)
        current = node

    if not instance.allowed[current][0]:
        return None
    leg = instance.distance[current][0]
    if not isfinite(leg):
        return None
    distance += leg
    cost += leg * instance.energy.energy_per_km
    if distance > instance.limits.max_battery_km + EPS:
        return None
    return Route(route_nodes, cost, distance, load, nodes_to_mask(route_nodes))


def split_permutation(instance: Instance, permutation: tuple[int, ...] | list[int], method: str = "Split") -> Solution:
    perm = tuple(permutation)
    n = len(perm)
    max_routes = instance.n_drones
    dp = [[inf for _ in range(max_routes + 1)] for _ in range(n + 1)]
    parent: list[list[tuple[int, int, Route] | None]] = [
        [None for _ in range(max_routes + 1)] for _ in range(n + 1)
    ]
    route_cache: dict[tuple[int, int], Route | None] = {}
    dp[0][0] = 0.0

    for start in range(n):
        active_counts = [count for count in range(max_routes) if dp[start][count] < inf]
        if not active_counts:
            continue
        load = 0.0
        for end in range(start + 1, n + 1):
            load += instance.demand(perm[end - 1])
            if load > instance.limits.max_payload + EPS:
                break
            key = (start, end)
            route = route_cache.get(key)
            if key not in route_cache:
                route = make_route(instance, perm[start:end])
                route_cache[key] = route
            if route is None:
                continue
            for count in active_counts:
                value = dp[start][count] + route.cost
                if value + EPS < dp[end][count + 1]:
                    dp[end][count + 1] = value
                    parent[end][count + 1] = (start, count, route)

    best_count = min(range(max_routes + 1), key=lambda count: dp[n][count])
    if dp[n][best_count] == inf:
        return Solution(method=method, routes=[], cost=inf, feasible=False)

    routes: list[Route] = []
    position = n
    count = best_count
    while position > 0:
        step = parent[position][count]
        if step is None:
            return Solution(method=method, routes=[], cost=inf, feasible=False)
        previous_position, previous_count, route = step
        routes.append(route)
        position = previous_position
        count = previous_count
    routes.reverse()
    return Solution(method=method, routes=routes, cost=dp[n][best_count], feasible=True)


def nearest_neighbor_permutation(instance: Instance) -> tuple[int, ...]:
    remaining = set(instance.customer_nodes)
    order: list[int] = []
    current = 0
    while remaining:
        next_node = min(remaining, key=lambda node: instance.distance[current][node])
        order.append(next_node)
        remaining.remove(next_node)
        current = next_node
    return tuple(order)
