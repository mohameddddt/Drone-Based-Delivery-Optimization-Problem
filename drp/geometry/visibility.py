"""Visibility-graph routing around polygonal no-fly zones (roadmap §4.1).

The old model deleted a blocked edge. That is wrong: a drone facing a restricted
zone does not give up on the customer behind it, it flies *around*. This module
replaces deletion with detour.

Method
------
Build a graph whose nodes are the depot, the customers, and every no-fly polygon
vertex. Two nodes are joined by an edge when the straight segment between them
does not enter any zone's interior; the edge weight is that segment's length.
The shortest obstacle-avoiding path between two sites is then a shortest path in
this graph -- a standard result, because an optimal path in a polygonal domain
turns only at obstacle vertices.

Running Dijkstra from each site gives the detoured distance matrix, which is
handed to the solvers as an ordinary distance matrix. **No solver changes at
all**: Branch & Bound, the GA, SA and ALNS all keep working, and simply see a
cost structure that now reflects real geography.

Cost
----
With `V` graph nodes this is O(V^2) for the visibility test and O(n V^2) for the
shortest paths. For the instance sizes here (tens of nodes, a handful of zones)
that is milliseconds, and it is computed once per instance and cached.
"""
from __future__ import annotations

import heapq
import math
from typing import List, Sequence, Tuple

import numpy as np

from drp.geometry.distance import distance_matrix
from drp.geometry.nofly import (Point, Polygon, point_in_any,
                                segment_blocked_by_any)


def build_visibility_graph(sites: Sequence[Point],
                           polys: Sequence[Polygon],
                           geodesic: bool = False) -> Tuple[List[Point], np.ndarray]:
    """Return ``(nodes, adjacency)`` for the visibility graph.

    `nodes` is the sites followed by every polygon vertex. `adjacency` holds
    edge lengths, with ``inf`` where two nodes cannot see each other.
    """
    nodes: List[Point] = [tuple(map(float, s)) for s in sites]
    for poly in polys:
        for v in poly:
            nodes.append((float(v[0]), float(v[1])))

    pts = np.array(nodes, dtype=float)
    base = distance_matrix(pts, geodesic=geodesic)

    m = len(nodes)
    adj = np.full((m, m), math.inf)
    for i in range(m):
        adj[i, i] = 0.0
        for j in range(i + 1, m):
            if not segment_blocked_by_any(nodes[i], nodes[j], polys):
                adj[i, j] = adj[j, i] = base[i, j]
    return nodes, adj


def _dijkstra(adj: np.ndarray, source: int) -> np.ndarray:
    m = adj.shape[0]
    dist = np.full(m, math.inf)
    dist[source] = 0.0
    visited = np.zeros(m, dtype=bool)
    heap = [(0.0, source)]
    while heap:
        d, u = heapq.heappop(heap)
        if visited[u]:
            continue
        visited[u] = True
        row = adj[u]
        for v in range(m):
            w = row[v]
            if w == math.inf or visited[v]:
                continue
            nd = d + w
            if nd < dist[v] - 1e-12:
                dist[v] = nd
                heapq.heappush(heap, (nd, v))
    return dist


def obstacle_distance_matrix(coords: np.ndarray,
                             polys: Sequence[Polygon],
                             geodesic: bool = False) -> np.ndarray:
    """Shortest obstacle-avoiding distance between every pair of sites.

    A site trapped inside a zone gets ``inf`` distances, which the feasibility
    layer reads as an unusable arc.
    """
    sites = [tuple(map(float, c)) for c in coords]
    if not polys:
        return distance_matrix(np.asarray(coords, dtype=float), geodesic=geodesic)

    nodes, adj = build_visibility_graph(sites, polys, geodesic=geodesic)
    n_sites = len(sites)

    out = np.full((n_sites, n_sites), math.inf)
    for i in range(n_sites):
        if point_in_any(sites[i], polys):
            continue  # unreachable; leave its row and column infinite
        d = _dijkstra(adj, i)
        out[i, :n_sites] = d[:n_sites]
    np.fill_diagonal(out, 0.0)
    # symmetrise against floating-point asymmetry in the searches
    return np.minimum(out, out.T)


def shortest_path(coords: np.ndarray,
                  polys: Sequence[Polygon],
                  i: int,
                  j: int,
                  geodesic: bool = False) -> List[Point]:
    """The actual detour polyline from site `i` to site `j`, for plotting."""
    sites = [tuple(map(float, c)) for c in coords]
    if not polys or not segment_blocked_by_any(sites[i], sites[j], polys):
        return [sites[i], sites[j]]

    nodes, adj = build_visibility_graph(sites, polys, geodesic=geodesic)
    m = len(nodes)
    dist = np.full(m, math.inf)
    prev = [-1] * m
    dist[i] = 0.0
    visited = np.zeros(m, dtype=bool)
    heap = [(0.0, i)]
    while heap:
        d, u = heapq.heappop(heap)
        if visited[u]:
            continue
        visited[u] = True
        if u == j:
            break
        for v in range(m):
            w = adj[u, v]
            if w == math.inf or visited[v]:
                continue
            if d + w < dist[v] - 1e-12:
                dist[v] = d + w
                prev[v] = u
                heapq.heappush(heap, (dist[v], v))

    if math.isinf(dist[j]):
        return [sites[i], sites[j]]
    path, cur = [], j
    while cur != -1:
        path.append(nodes[cur])
        cur = prev[cur]
    return list(reversed(path))
