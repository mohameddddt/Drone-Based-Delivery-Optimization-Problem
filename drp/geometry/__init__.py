"""Geometry: distance metrics, no-fly polygons, visibility-graph detours."""
from drp.geometry.distance import (distance_matrix, euclidean_matrix,
                                   haversine_matrix)
from drp.geometry.nofly import (circle_polygon, point_in_any, point_in_polygon,
                                rect_polygon, segment_blocked,
                                segment_blocked_by_any)
from drp.geometry.visibility import (build_visibility_graph,
                                     obstacle_distance_matrix, shortest_path)

__all__ = [
    "distance_matrix", "euclidean_matrix", "haversine_matrix",
    "point_in_polygon", "point_in_any", "segment_blocked",
    "segment_blocked_by_any", "circle_polygon", "rect_polygon",
    "obstacle_distance_matrix", "build_visibility_graph", "shortest_path",
]
