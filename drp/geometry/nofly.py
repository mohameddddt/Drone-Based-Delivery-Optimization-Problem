"""Polygonal no-fly zones -- the primitives.

A zone is a simple polygon given as a list of ``(x, y)`` vertices in order. The
functions here answer two questions:

  * is this point inside a zone?  (a customer there is unreachable)
  * does this straight segment cut through a zone?  (so the leg needs a detour)

`drp.geometry.visibility` builds on these to compute detoured distances.

Note the deliberate boundary convention: touching a zone's edge or grazing a
vertex is allowed. Without it, a detour path -- which by construction runs along
zone boundaries -- would be judged to collide with the very obstacle it is
skirting.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

Point = Tuple[float, float]
Polygon = Sequence[Point]

EPS = 1e-9


def _orient(a: Point, b: Point, c: Point) -> float:
    """Twice the signed area of triangle abc. >0 counter-clockwise."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: Point, b: Point, p: Point) -> bool:
    """True if `p` lies on segment ab, assuming the three are collinear."""
    return (min(a[0], b[0]) - EPS <= p[0] <= max(a[0], b[0]) + EPS
            and min(a[1], b[1]) - EPS <= p[1] <= max(a[1], b[1]) + EPS)


def segments_properly_cross(a: Point, b: Point, c: Point, d: Point) -> bool:
    """True if segment ab and segment cd cross at an interior point.

    Touching endpoints and collinear overlap return False: those are the cases a
    boundary-following detour path relies on.
    """
    d1, d2 = _orient(c, d, a), _orient(c, d, b)
    d3, d4 = _orient(a, b, c), _orient(a, b, d)

    if ((d1 > EPS and d2 < -EPS) or (d1 < -EPS and d2 > EPS)) and \
       ((d3 > EPS and d4 < -EPS) or (d3 < -EPS and d4 > EPS)):
        return True
    return False


def point_in_polygon(p: Point, poly: Polygon) -> bool:
    """Ray-casting test. Points on the boundary count as outside."""
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if abs(_orient(a, b, p)) < EPS and _on_segment(a, b, p):
            return False  # on the boundary

    inside = False
    x, y = p
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_cross:
                inside = not inside
    return inside


def segment_blocked(a: Point, b: Point, poly: Polygon) -> bool:
    """True if travelling straight from `a` to `b` enters `poly`'s interior."""
    n = len(poly)
    for i in range(n):
        c, d = poly[i], poly[(i + 1) % n]
        if segments_properly_cross(a, b, c, d):
            return True

    # A segment can lie wholly inside without crossing any edge. Sampling the
    # midpoint catches that, and also the case where both endpoints sit on the
    # boundary but the chord cuts across the interior (a reflex polygon).
    mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    return point_in_polygon(mid, poly)


def segment_blocked_by_any(a: Point, b: Point, polys: Sequence[Polygon]) -> bool:
    return any(segment_blocked(a, b, p) for p in polys)


def point_in_any(p: Point, polys: Sequence[Polygon]) -> bool:
    return any(point_in_polygon(p, poly) for poly in polys)


def circle_polygon(cx: float, cy: float, radius: float, sides: int = 12) -> List[Point]:
    """Approximate a circular zone (a stadium, a helipad) as a polygon."""
    import math
    return [(cx + radius * math.cos(2 * math.pi * k / sides),
             cy + radius * math.sin(2 * math.pi * k / sides))
            for k in range(sides)]


def rect_polygon(x0: float, y0: float, x1: float, y1: float) -> List[Point]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
