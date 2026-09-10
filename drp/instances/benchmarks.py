"""Importers for the standard VRP benchmark libraries (roadmap §3.3).

Two formats, both plain text and both decades old:

``cvrplib`` / TSPLIB
    The ``.vrp`` files behind CVRPLIB (Augerat, Christofides, Uchoa, ...).
    Key-value header, then ``NODE_COORD_SECTION``, ``DEMAND_SECTION`` and
    ``DEPOT_SECTION``. The published optimum, when the file's ``COMMENT``
    carries one, is parsed out alongside the instance.

``solomon``
    The VRPTW files (C101, R201, ...): a ``VEHICLE`` block giving fleet size and
    capacity, then one row per node with coordinates, demand, a time window and
    a service time.

Why this matters here
---------------------
Every number in this project so far comes from instances it generated itself.
Importing literature instances does two things the synthetic suite cannot: it
lets the solvers be checked against *published optima* rather than only against
this repository's own brute force, and it supplies the larger paired sample that
§6's significance testing needs to separate GA, SA and ALNS.

Faithfulness, stated plainly
----------------------------
* **CVRP is this problem at ``beta = 0``.** With no load term the energy of a
  route is exactly its distance, the payload cap is the vehicle capacity and the
  battery is unbounded -- so an imported CVRP instance solved here *is* the
  classic problem, and its objective is directly comparable to the published
  optimum. Give ``beta > 0`` instead and you get a drone instance built on real
  benchmark geography, which is no longer comparable to anything published.
* **Rounded distances.** CVRPLIB's ``EUC_2D`` metric is the Euclidean distance
  *rounded to the nearest integer*, and its optima are defined on that metric.
  ``round_distances=True`` (the default for this format) reproduces it; without
  it, a "gap to best known" is a gap between two different problems.
* **Time windows are dropped.** Solomon instances are VRPTW; this model has no
  time dimension (roadmap §4.4). The windows and service times are parsed and
  handed back on the `ImportedInstance` so nothing is silently lost, but the
  instance itself ignores them -- which means a Solomon import is a *relaxation*
  of the published problem, and its optimum is a lower bound on the VRPTW
  optimum rather than a target to match. ``dropped`` records this on every
  import.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from drp.core.instance import DRPInstance

PathLike = Union[str, Path]


@dataclass
class ImportedInstance:
    """An instance, plus everything the import could not put inside it."""

    instance: DRPInstance
    source: str
    fmt: str
    best_known: Optional[float] = None
    best_known_kind: Optional[str] = None      # "optimal" | "best known"
    declared_vehicles: Optional[int] = None
    dropped: Tuple[str, ...] = ()
    extras: Dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        """One line naming the instance. What was *dropped* is reported
        separately, because it is the part a reader must not skim."""
        parts = [f"{self.instance.name}: n={self.instance.n_customers}, "
                 f"K={self.instance.n_drones}, capacity={self.instance.payload:g}"]
        if self.best_known is not None:
            parts.append(f"{self.best_known_kind or 'reference'} value "
                         f"{self.best_known:g}")
        return "  |  ".join(parts)


# ---------------------------------------------------------------------------
# CVRPLIB / TSPLIB
# ---------------------------------------------------------------------------
_HEADER_RE = re.compile(r"^\s*([A-Z_]+)\s*:\s*(.*?)\s*$")
_HEADER_KEYS = ("NAME", "TYPE", "DIMENSION", "CAPACITY", "COMMENT",
                "EDGE_WEIGHT_TYPE", "VEHICLES")


def parse_cvrplib(text: str) -> Dict[str, Any]:
    """Split a TSPLIB-style file into its headers and its sections.

    Returns ``{"headers": {...}, "sections": {name: [line, ...]}}`` with no
    interpretation applied, so a caller can inspect an unsupported file.
    """
    headers: Dict[str, str] = {}
    sections: Dict[str, List[str]] = {}
    current: Optional[str] = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.endswith("_SECTION"):
            current = upper
            sections.setdefault(current, [])
            continue
        if upper == "EOF":
            break
        m = _HEADER_RE.match(line)
        if m and (current is None or m.group(1).upper() in _HEADER_KEYS):
            headers[m.group(1).upper()] = m.group(2)
            continue
        if current is None:
            continue
        sections[current].append(line)
    return {"headers": headers, "sections": sections}


def _parse_reference_value(comment: str) -> Tuple[Optional[float], Optional[str]]:
    """Pull ``Optimal value: 784`` / ``Best value: 1291`` out of a COMMENT."""
    m = re.search(r"(optimal|best[ -]known|best)\s+value\s*:?\s*"
                  r"([0-9]+(?:\.[0-9]+)?)", comment, re.IGNORECASE)
    if not m:
        return None, None
    kind = "optimal" if m.group(1).lower().startswith("optimal") else "best known"
    return float(m.group(2)), kind


def _parse_truck_count(comment: str) -> Optional[int]:
    m = re.search(r"(?:no\.?\s*of\s*trucks|vehicles|trucks)\s*:?\s*([0-9]+)",
                  comment, re.IGNORECASE)
    return int(m.group(1)) if m else None


def read_cvrplib(path: PathLike,
                 n_drones: Optional[int] = None,
                 alpha: float = 1.0,
                 beta: float = 0.0,
                 battery: float = math.inf,
                 round_distances: bool = True,
                 name: Optional[str] = None) -> ImportedInstance:
    """Read a CVRPLIB ``.vrp`` file into a `DRPInstance`.

    The defaults reproduce the classic problem exactly: ``beta = 0`` (a pure
    distance objective), an unbounded battery, and rounded ``EUC_2D``
    distances. The fleet size comes from `n_drones`, else the file's declared
    truck count, else the smallest number of vehicles that can carry the total
    demand.
    """
    p = Path(path)
    parsed = parse_cvrplib(p.read_text(encoding="utf-8", errors="replace"))
    headers, sections = parsed["headers"], parsed["sections"]

    kind = headers.get("TYPE", "CVRP").upper()
    if kind not in ("CVRP", "TSP", "ACVRP"):
        raise ValueError(f"{p.name}: unsupported TSPLIB TYPE {kind!r}; "
                         "this importer reads CVRP and TSP files")

    weight_type = headers.get("EDGE_WEIGHT_TYPE", "EUC_2D").upper()
    if weight_type != "EUC_2D":
        raise ValueError(
            f"{p.name}: EDGE_WEIGHT_TYPE {weight_type!r} is not supported. "
            "Only EUC_2D is; an explicit weight matrix or a GEO metric would "
            "need a distance hook this model does not have.")
    if "NODE_COORD_SECTION" not in sections:
        raise ValueError(f"{p.name}: no NODE_COORD_SECTION")

    coord_by_id: Dict[int, Tuple[float, float]] = {}
    for line in sections["NODE_COORD_SECTION"]:
        parts = line.split()
        coord_by_id[int(parts[0])] = (float(parts[1]), float(parts[2]))

    demand_by_id: Dict[int, float] = {}
    for line in sections.get("DEMAND_SECTION", []):
        parts = line.split()
        demand_by_id[int(parts[0])] = float(parts[1])

    depot_ids = [int(x) for line in sections.get("DEPOT_SECTION", [])
                 for x in line.split() if int(x) > 0]
    if not depot_ids:
        depot_ids = [min(coord_by_id)]
    if len(depot_ids) > 1:
        raise ValueError(f"{p.name}: {len(depot_ids)} depots; this model has one")
    depot_id = depot_ids[0]

    customer_ids = [i for i in sorted(coord_by_id) if i != depot_id]
    n = len(customer_ids)
    coords = np.zeros((n + 1, 2), dtype=float)
    demand = np.zeros(n + 1, dtype=float)
    coords[0] = coord_by_id[depot_id]
    for k, cid in enumerate(customer_ids, start=1):
        coords[k] = coord_by_id[cid]
        demand[k] = demand_by_id.get(cid, 0.0)

    dimension = int(headers.get("DIMENSION", n + 1))
    if dimension != n + 1:
        raise ValueError(f"{p.name}: DIMENSION says {dimension} nodes but "
                         f"{n + 1} coordinates were read")

    capacity = float(headers.get("CAPACITY", demand.sum() or 1.0))
    comment = headers.get("COMMENT", "")
    best, best_kind = _parse_reference_value(comment)
    declared = _parse_truck_count(comment)
    if declared is None and "VEHICLES" in headers:
        declared = int(headers["VEHICLES"])

    fleet = n_drones or declared or math.ceil(demand.sum() / capacity)

    inst = DRPInstance(
        name=name or headers.get("NAME", p.stem),
        n_customers=n,
        n_drones=int(max(1, fleet)),
        coords=coords,
        demand=demand,
        battery=battery,
        payload=max(capacity, float(demand.max()) if n else capacity),
        alpha=alpha,
        beta=beta,
        round_distances=round_distances,
    )

    dropped: List[str] = []
    if beta != 0.0:
        dropped.append("the published objective (beta > 0 makes this a drone "
                       "instance, not the CVRP the optimum refers to)")
    if not math.isinf(battery):
        dropped.append("unbounded range (a battery cap is not part of CVRP)")
    if not round_distances:
        dropped.append("the rounded EUC_2D metric the optimum is defined on")

    return ImportedInstance(
        instance=inst, source=str(p), fmt="cvrplib",
        best_known=best, best_known_kind=best_kind,
        declared_vehicles=declared, dropped=tuple(dropped),
        extras={"comment": comment, "capacity": capacity,
                "customer_ids": customer_ids, "depot_id": depot_id},
    )


# ---------------------------------------------------------------------------
# Solomon VRPTW
# ---------------------------------------------------------------------------
def read_solomon(path: PathLike,
                 n_customers: Optional[int] = None,
                 n_drones: Optional[int] = None,
                 alpha: float = 1.0,
                 beta: float = 0.0,
                 battery: float = math.inf,
                 name: Optional[str] = None) -> ImportedInstance:
    """Read a Solomon VRPTW file, **dropping the time windows**.

    `n_customers` truncates to the first ``N`` customers, which is how the
    standard reduced sets (C101-25, C101-50) are defined. The dropped windows
    and service times come back in ``extras`` so a later time-window model
    (roadmap §4.4) can pick them up without re-parsing.
    """
    p = Path(path)
    stripped = [ln.strip() for ln in
                p.read_text(encoding="utf-8", errors="replace").splitlines()]

    try:
        v_at = next(i for i, ln in enumerate(stripped) if ln.upper() == "VEHICLE")
        c_at = next(i for i, ln in enumerate(stripped) if ln.upper() == "CUSTOMER")
    except StopIteration as exc:
        raise ValueError(f"{p.name}: not a Solomon file "
                         "(no VEHICLE / CUSTOMER block)") from exc

    header_name = next((ln for ln in stripped[:v_at] if ln), p.stem)

    fleet_numbers: List[float] = []
    for ln in stripped[v_at + 1:c_at]:
        parts = ln.split()
        if parts and all(_is_number(x) for x in parts):
            fleet_numbers = [float(x) for x in parts]
            break
    if len(fleet_numbers) < 2:
        raise ValueError(f"{p.name}: could not read NUMBER / CAPACITY")
    declared, capacity = int(fleet_numbers[0]), float(fleet_numbers[1])

    rows: List[List[float]] = []
    for ln in stripped[c_at + 1:]:
        parts = ln.split()
        if len(parts) >= 7 and all(_is_number(x) for x in parts[:7]):
            rows.append([float(x) for x in parts[:7]])
    if not rows:
        raise ValueError(f"{p.name}: no customer rows")

    depot_row, customer_rows = rows[0], rows[1:]
    if n_customers is not None:
        customer_rows = customer_rows[:n_customers]
    n = len(customer_rows)

    coords = np.zeros((n + 1, 2), dtype=float)
    demand = np.zeros(n + 1, dtype=float)
    coords[0] = (depot_row[1], depot_row[2])
    for k, row in enumerate(customer_rows, start=1):
        coords[k] = (row[1], row[2])
        demand[k] = row[3]

    fleet = n_drones or _solomon_fleet(declared, float(demand.sum()), capacity)
    inst = DRPInstance(
        name=name or (header_name if n_customers is None
                      else f"{header_name}-{n}"),
        n_customers=n,
        n_drones=int(max(1, fleet)),
        coords=coords,
        demand=demand,
        battery=battery,
        payload=max(capacity, float(demand.max()) if n else capacity),
        alpha=alpha,
        beta=beta,
    )

    return ImportedInstance(
        instance=inst, source=str(p), fmt="solomon",
        best_known=None, declared_vehicles=declared,
        dropped=("time windows", "service times",
                 "the declared vehicle count as a hard constraint"),
        extras={"depot_window": (depot_row[4], depot_row[5]),
                "time_windows": [(row[4], row[5]) for row in customer_rows],
                "service_times": [row[6] for row in customer_rows],
                "capacity": capacity},
    )


def _solomon_fleet(declared: int, total_demand: float, capacity: float) -> int:
    """Solomon files declare 25 vehicles for a 25-customer problem.

    That is a *ceiling*, not a fleet: taking it literally would allow one drone
    per customer and make the partitioning decision vacuous. Use the capacity
    lower bound with one spare vehicle, and never more than declared.
    """
    needed = math.ceil(total_demand / capacity) if capacity > 0 else declared
    return max(1, min(declared, needed + 1))


def _is_number(token: str) -> bool:
    try:
        float(token)
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------------------
def read_benchmark(path: PathLike, fmt: str = "auto", **kwargs) -> ImportedInstance:
    """Read a benchmark file, sniffing the format when `fmt` is ``"auto"``."""
    p = Path(path)
    if fmt == "auto":
        head = p.read_text(encoding="utf-8", errors="replace")[:4000].upper()
        if "NODE_COORD_SECTION" in head or p.suffix.lower() == ".vrp":
            fmt = "cvrplib"
        elif "CUSTOMER" in head and "VEHICLE" in head:
            fmt = "solomon"
        else:
            raise ValueError(f"{p.name}: cannot tell which benchmark format "
                             "this is; pass the format explicitly")
    if fmt == "cvrplib":
        return read_cvrplib(p, **kwargs)
    if fmt == "solomon":
        return read_solomon(p, **kwargs)
    raise ValueError(f"unknown benchmark format {fmt!r}")


def read_benchmark_suite(paths: Sequence[PathLike],
                         fmt: str = "auto",
                         **kwargs) -> List[ImportedInstance]:
    """Read several benchmark files, keeping the order given."""
    return [read_benchmark(p, fmt=fmt, **kwargs) for p in paths]


def benchmark_directory(root: PathLike,
                        pattern: str = "*.vrp",
                        fmt: str = "auto",
                        limit: Optional[int] = None,
                        **kwargs) -> List[ImportedInstance]:
    """Every benchmark file under `root`, ordered by size then name.

    Sorting by `n` matters: it makes a suite's results read as a size sweep,
    and it puts the instances a solver can still prove first.
    """
    files = sorted(Path(root).rglob(pattern))
    if not files:
        raise FileNotFoundError(f"no {pattern} files under {root}")
    suite = read_benchmark_suite(files, fmt=fmt, **kwargs)
    suite.sort(key=lambda imp: (imp.instance.n_customers, imp.instance.name))
    return suite[:limit] if limit else suite


# ---------------------------------------------------------------------------
# Published solutions
# ---------------------------------------------------------------------------
@dataclass
class PublishedSolution:
    """A ``.sol`` file: somebody else's answer, and what they scored it."""

    routes: List[List[int]]
    cost: Optional[float]
    source: str

    def solution(self) -> "Solution":
        from drp.core.solution import Solution

        return Solution([list(r) for r in self.routes])


_ROUTE_RE = re.compile(r"^\s*Route\s*#\s*\d+\s*:(.*)$", re.IGNORECASE)


def read_cvrplib_solution(path: PathLike) -> PublishedSolution:
    """Read a CVRPLIB ``.sol`` file.

    The customer numbering lines up with this package's own: a ``.sol`` lists
    customers 1..n in the file's node order excluding the depot, which is
    exactly how `read_cvrplib` indexes them. So a published solution can be
    dropped straight into `Solution` and scored -- which is what
    `tests/test_cvrplib_published.py` does to check this project's objective
    against 74 answers it had no hand in producing.
    """
    p = Path(path)
    routes: List[List[int]] = []
    cost: Optional[float] = None
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _ROUTE_RE.match(line)
        if m:
            routes.append([int(x) for x in m.group(1).split()])
            continue
        if line.strip().lower().startswith("cost"):
            parts = line.split()
            if parts:
                try:
                    cost = float(parts[-1])
                except ValueError:
                    pass
    if not routes:
        raise ValueError(f"{p.name}: no 'Route #k:' lines")
    return PublishedSolution(routes=routes, cost=cost, source=str(p))


def solution_path_for(instance_file: PathLike) -> Optional[Path]:
    """The ``.sol`` sitting beside a ``.vrp``, if the set shipped one."""
    p = Path(instance_file).with_suffix(".sol")
    return p if p.exists() else None
