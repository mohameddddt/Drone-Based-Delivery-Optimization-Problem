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


def boundary_crossings(a: Point, b: Point, poly: Polygon) -> List[float]:
    """Parameters ``t`` in ``[0, 1]`` where segment ab meets `poly`'s boundary.

    Touching a vertex counts, and so does a collinear overlap with an edge --
    the point is to find every place the segment could pass from outside to
    inside, not only the transversal crossings.
    """
    ax, ay = a
    rx, ry = b[0] - ax, b[1] - ay
    rr = rx * rx + ry * ry
    if rr < EPS * EPS:
        return []

    ts: List[float] = []
    n = len(poly)
    for i in range(n):
        c, d = poly[i], poly[(i + 1) % n]
        sx, sy = d[0] - c[0], d[1] - c[1]
        cax, cay = c[0] - ax, c[1] - ay
        denom = rx * sy - ry * sx
        if abs(denom) > EPS:
            t = (cax * sy - cay * sx) / denom
            u = (cax * ry - cay * rx) / denom
            if -EPS <= t <= 1 + EPS and -EPS <= u <= 1 + EPS:
                ts.append(min(1.0, max(0.0, t)))
        elif abs(cax * ry - cay * rx) <= EPS:      # collinear with this edge
            for px, py in (c, d):
                t = ((px - ax) * rx + (py - ay) * ry) / rr
                if -EPS <= t <= 1 + EPS:
                    ts.append(min(1.0, max(0.0, t)))
    return ts


def segment_blocked(a: Point, b: Point, poly: Polygon) -> bool:
    """True if travelling straight from `a` to `b` enters `poly`'s interior.

    The segment is cut at every point where it meets the boundary, and each
    resulting piece is classified by its own midpoint. Testing only the whole
    segment's midpoint is not enough: a chord that enters and leaves through
    two *vertices* -- the depot, a zone and a customer in a straight line, which
    a symmetric layout produces easily -- crosses no edge properly and can have
    its midpoint outside the zone, and was previously judged clear.
    """
    ts = sorted({0.0, 1.0, *boundary_crossings(a, b, poly)})
    for t0, t1 in zip(ts, ts[1:]):
        if t1 - t0 < EPS:
            continue
        t = (t0 + t1) / 2.0
        mid = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        if point_in_polygon(mid, poly):
            return True
    return False


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
