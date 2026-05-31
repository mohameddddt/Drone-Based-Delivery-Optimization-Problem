from __future__ import annotations

from math import hypot


def euclidean(a: tuple[float, float], b: tuple[float, float]) -> float:
    return hypot(a[0] - b[0], a[1] - b[1])


def segment_intersects_circle(
    a: tuple[float, float],
    b: tuple[float, float],
    center: tuple[float, float],
    radius: float,
) -> bool:
    ax, ay = a
    bx, by = b
    cx, cy = center
    dx = bx - ax
    dy = by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return euclidean(a, center) <= radius
    t = ((cx - ax) * dx + (cy - ay) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    nearest = (ax + t * dx, ay + t * dy)
    return euclidean(nearest, center) <= radius
