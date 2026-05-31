from __future__ import annotations

from functools import lru_cache
from math import ceil, inf
from time import perf_counter

from .models import Instance, Route, Solution
from .routing import EPS, make_route, nearest_neighbor_permutation, split_permutation


def solve_branch_and_bound(instance: Instance, time_limit: float = 60.0) -> Solution:
    started = perf_counter()
    routes = enumerate_routes(instance)
    full_mask = instance.full_mask
    if not routes:
        return Solution("Branch and Bound", [], inf, False, runtime_sec=perf_counter() - started)

    by_customer: dict[int, list[Route]] = {node: [] for node in instance.customer_nodes}
    for route in routes:
        for node in route.nodes:
            by_customer[node].append(route)
    for node, customer_routes in by_customer.items():
        if not customer_routes:
            return Solution("Branch and Bound", [], inf, False, runtime_sec=perf_counter() - started)
        customer_routes.sort(key=lambda route: (route.cost / route.size, route.cost))

    initial = _initial_solution(instance, routes, by_customer)
    best_routes = initial.routes if initial.feasible else []
    best_cost = initial.cost if initial.feasible else inf
    min_share = {
        node: min(route.cost / route.size for route in by_customer[node])
        for node in instance.customer_nodes
    }
    explored = 0
    timed_out = False

    @lru_cache(maxsize=None)
    def demand_for_mask(mask: int) -> float:
        total = 0.0
        for node in instance.customer_nodes:
            if mask & (1 << (node - 1)):
                total += instance.demand(node)
        return total

    def lower_bound(mask: int, cost: float) -> float:
        value = cost
        uncovered = full_mask & ~mask
        for node in instance.customer_nodes:
            if uncovered & (1 << (node - 1)):
                value += min_share[node]
        return value

    def choose_customer(mask: int) -> tuple[int | None, list[Route]]:
        best_node: int | None = None
        best_candidates: list[Route] = []
        for node in instance.customer_nodes:
            if mask & (1 << (node - 1)):
                continue
            candidates = [route for route in by_customer[node] if route.mask & mask == 0]
            if not candidates:
                return node, []
            if best_node is None or len(candidates) < len(best_candidates):
                best_node = node
                best_candidates = candidates
        return best_node, best_candidates

    def search(mask: int, count: int, cost: float, selected: list[Route]) -> None:
        nonlocal best_cost, best_routes, explored, timed_out
        if timed_out:
            return
        if perf_counter() - started > time_limit:
            timed_out = True
            return
        explored += 1
        if mask == full_mask:
            if cost + EPS < best_cost:
                best_cost = cost
                best_routes = list(selected)
            return
        if count >= instance.n_drones:
            return
        uncovered = full_mask & ~mask
        remaining_demand = demand_for_mask(uncovered)
        minimum_routes = ceil(max(0.0, remaining_demand - EPS) / instance.limits.max_payload)
        if count + minimum_routes > instance.n_drones:
            return
        if lower_bound(mask, cost) >= best_cost - EPS:
            return

        node, candidates = choose_customer(mask)
        if node is None or not candidates:
            return
        for route in candidates:
            if route.mask & mask:
                continue
            next_cost = cost + route.cost
            if next_cost >= best_cost - EPS:
                continue
            selected.append(route)
            search(mask | route.mask, count + 1, next_cost, selected)
            selected.pop()

    search(0, 0, 0.0, [])
    runtime = perf_counter() - started
    feasible = best_cost < inf
    optimal = feasible and not timed_out
    lower = best_cost if optimal else lower_bound(0, 0.0)
    gap = None
    if feasible and lower is not None and best_cost > EPS:
        gap = max(0.0, (best_cost - lower) / best_cost * 100.0)
    return Solution(
        method="Branch and Bound",
        routes=best_routes,
        cost=best_cost,
        feasible=feasible,
        runtime_sec=runtime,
        iterations=explored,
        optimal=optimal,
        lower_bound=lower,
        gap_percent=gap,
        explored_nodes=explored,
    )


def enumerate_routes(instance: Instance) -> list[Route]:
    best_by_mask: dict[int, Route] = {}
    path: list[int] = []
    nodes = instance.customer_nodes

    def visit(current: int, mask: int, load: float, distance_so_far: float) -> None:
        if path:
            route = make_route(instance, path)
            if route is not None:
                best = best_by_mask.get(route.mask)
                if best is None or route.cost + EPS < best.cost:
                    best_by_mask[route.mask] = route
        for node in nodes:
            bit = 1 << (node - 1)
            if mask & bit:
                continue
            new_load = load + instance.demand(node)
            if new_load > instance.limits.max_payload + EPS:
                continue
            if not instance.allowed[current][node]:
                continue
            leg = instance.distance[current][node]
            if distance_so_far + leg > instance.limits.max_battery_km + EPS:
                continue
            path.append(node)
            visit(node, mask | bit, new_load, distance_so_far + leg)
            path.pop()

    visit(0, 0, 0.0, 0.0)
    return sorted(best_by_mask.values(), key=lambda route: (route.size, route.cost))


def _initial_solution(
    instance: Instance,
    routes: list[Route],
    by_customer: dict[int, list[Route]],
) -> Solution:
    nearest = split_permutation(instance, nearest_neighbor_permutation(instance), method="Initial")
    best = nearest
    full_mask = instance.full_mask
    selected: list[Route] = []
    mask = 0
    while mask != full_mask and len(selected) < instance.n_drones:
        uncovered_nodes = [
            node for node in instance.customer_nodes if not (mask & (1 << (node - 1)))
        ]
        node = min(uncovered_nodes, key=lambda candidate: len(by_customer[candidate]))
        candidates = [route for route in by_customer[node] if route.mask & mask == 0]
        if not candidates:
            break
        route = min(candidates, key=lambda candidate: candidate.cost / candidate.size)
        selected.append(route)
        mask |= route.mask
    if mask == full_mask:
        cost = sum(route.cost for route in selected)
        greedy = Solution("Initial", selected, cost, True)
        if not best.feasible or greedy.cost < best.cost:
            best = greedy
    return best
