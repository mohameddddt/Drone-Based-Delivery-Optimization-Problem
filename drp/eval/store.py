"""The results store (roadmap §1.5).

Every solver run appends one row to a SQLite database. Figures, tables and the
report all read from it, so no number is ever typed by hand and every claim is
traceable to the commit that produced it.

Columns are exactly the roadmap's list -- instance, method, seed, time_budget,
energy, feasible, nodes, wall_time, git_sha -- plus the dual bound and the
optimality flag from Branch & Bound.

SQLite rather than Parquet: it is in the standard library, so the store has no
dependencies and can be queried from anywhere without a pandas install.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

PathLike = Union[str, Path]

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_group    TEXT,
    instance     TEXT NOT NULL,
    n            INTEGER,
    k            INTEGER,
    method       TEXT NOT NULL,
    seed         INTEGER,
    time_budget  REAL,
    energy       REAL,
    dual_bound   REAL,
    optimal      INTEGER,
    feasible     INTEGER,
    nodes        INTEGER,
    iterations   INTEGER,
    wall_time    REAL,
    git_sha      TEXT,
    created_at   REAL,
    extra        TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_instance ON runs(instance);
CREATE INDEX IF NOT EXISTS idx_runs_method ON runs(method);
CREATE INDEX IF NOT EXISTS idx_runs_group ON runs(run_group);
"""


def git_sha(short: bool = True) -> str:
    """The commit the code is running from, or 'unknown' outside a repo."""
    try:
        args = ["git", "rev-parse"] + (["--short"] if short else []) + ["HEAD"]
        out = subprocess.run(args, capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            sha = out.stdout.strip()
            dirty = subprocess.run(["git", "status", "--porcelain"],
                                   capture_output=True, text=True, timeout=5)
            if dirty.returncode == 0 and dirty.stdout.strip():
                sha += "-dirty"
            return sha
    except Exception:
        pass
    return "unknown"


@dataclass
class RunRecord:
    instance: str
    method: str
    n: Optional[int] = None
    k: Optional[int] = None
    seed: Optional[int] = None
    time_budget: Optional[float] = None
    energy: Optional[float] = None
    dual_bound: Optional[float] = None
    optimal: bool = False
    feasible: bool = True
    nodes: Optional[int] = None
    iterations: Optional[int] = None
    wall_time: Optional[float] = None
    run_group: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class ResultStore:
    """Append-only SQLite store of solver runs."""

    def __init__(self, path: PathLike = "results/runs.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._sha = git_sha()

    def add(self, rec: RunRecord) -> None:
        d = asdict(rec)
        self.conn.execute(
            """INSERT INTO runs (run_group, instance, n, k, method, seed,
                                 time_budget, energy, dual_bound, optimal,
                                 feasible, nodes, iterations, wall_time,
                                 git_sha, created_at, extra)
               VALUES (:run_group, :instance, :n, :k, :method, :seed,
                       :time_budget, :energy, :dual_bound, :optimal,
                       :feasible, :nodes, :iterations, :wall_time,
                       :git_sha, :created_at, :extra)""",
            {**d,
             "optimal": int(rec.optimal),
             "feasible": int(rec.feasible),
             "extra": json.dumps(rec.extra),
             "git_sha": self._sha,
             "created_at": time.time()},
        )
        self.conn.commit()

    def add_many(self, recs: Iterable[RunRecord]) -> None:
        for r in recs:
            self.add(r)

    def rows(self, run_group: Optional[str] = None) -> List[Dict[str, Any]]:
        if run_group:
            cur = self.conn.execute(
                "SELECT * FROM runs WHERE run_group = ? ORDER BY id", (run_group,))
        else:
            cur = self.conn.execute("SELECT * FROM runs ORDER BY id")
        return [dict(r) for r in cur.fetchall()]

    def latest_group(self) -> Optional[str]:
        cur = self.conn.execute(
            "SELECT run_group FROM runs ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        return row["run_group"] if row else None

    def methods(self, run_group: Optional[str] = None) -> List[str]:
        rows = self.rows(run_group)
        seen, out = set(), []
        for r in rows:
            if r["method"] not in seen:
                seen.add(r["method"])
                out.append(r["method"])
        return out

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "ResultStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
