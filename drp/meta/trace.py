"""Search traces for the metaheuristics (roadmap §2.4, convergence dashboards).

The same discipline as `drp.exact.bnb`'s tree trace: **opt-in, off by default,
one guard per recording site, and it may not change what the solver returns.**
`bench` and `compare` run these under a time limit and must not regress.

Why a trace at all when there is already `history`
-------------------------------------------------
All three metaheuristics already record `history: List[float]` -- best-so-far,
subsampled (every 50 iterations for ALNS, every 200 for SA, every generation for
GA). That is enough to draw a monotone staircase and nothing else. It cannot
show why the staircase has the shape it does:

* **SA** looks like SA because of the *working* solution wandering above the
  best-so-far, and because of the temperature schedule driving how far it is
  allowed to wander. `history` has neither.
* **ALNS** is *adaptive*; the thing worth watching is the operator weights
  moving as the search learns which destroy/repair pair is paying. Only the
  final weights were reported.
* **GA** is a *population*; a best-of-generation line says nothing about whether
  the population converged or collapsed.

So a sample carries the working energy, the temperature, and the per-method
extras, and the x-axis carries elapsed seconds as well as the step index --
without wall-clock time you cannot honestly compare a GA generation against an
SA iteration.

Keeping it bounded
------------------
SA runs tens of thousands of iterations. Recording every one would put megabytes
into a browser page for a curve a few thousand points wide. `MetaTracer`
therefore **decimates**: it records every `stride`-th step, and whenever the
buffer reaches `max_samples` it discards every second sample and doubles the
stride. The result is a uniform sample of the *whole* run at all times -- not a
truncated prefix, which for a convergence curve would be the one useless
shape -- and it costs O(1) amortised per step. The stride that survived is
reported, so the page can say what it is showing.

Events (a new best, a reheat) are rare and are recorded separately and in full,
so decimation never drops one.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

#: A sample's `event` values, and what they mean for the working solution.
SAMPLE_EVENTS = ("new_best", "improved", "accepted", "rejected", "infeasible",
                 "generation")
#: Standalone events, recorded in full rather than decimated.
EVENT_KINDS = ("new_best", "reheat", "restart")


def _f(v: Optional[float]) -> Optional[float]:
    """JSON-safe: JSON has no Infinity, and an absent value is not a number."""
    if v is None or not isinstance(v, (int, float)) or not math.isfinite(v):
        return None
    return float(v)


@dataclass
class MetaSample:
    """One recorded step of a search.

    `current` is the energy of the *working* solution -- the one the search
    would perturb next. For GA, which has no single working solution, it is the
    best of that generation's population, and `mean`/`spread` describe the rest.
    `temperature` and `accepted` are None for methods that have no such notion.
    """
    step: int
    t: float                              # seconds since the search started
    best: float
    current: float
    event: str = ""
    temperature: Optional[float] = None
    accepted: Optional[bool] = None
    op_destroy: Optional[int] = None      # ALNS: index into DESTROY_OPS
    op_repair: Optional[int] = None       # ALNS: index into REPAIR_OPS
    mean: Optional[float] = None          # GA: population mean energy
    spread: Optional[float] = None        # GA: population energy spread

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"step": int(self.step), "t": round(float(self.t), 4),
                             "best": _f(self.best), "current": _f(self.current)}
        if self.event:
            d["event"] = self.event
        if self.temperature is not None:
            d["temp"] = _f(self.temperature)
        if self.accepted is not None:
            d["acc"] = bool(self.accepted)
        if self.op_destroy is not None:
            d["od"] = int(self.op_destroy)
        if self.op_repair is not None:
            d["or"] = int(self.op_repair)
        if self.mean is not None:
            d["mean"] = _f(self.mean)
        if self.spread is not None:
            d["spread"] = _f(self.spread)
        return d


@dataclass
class MetaEvent:
    """Something that happened once, recorded in full."""
    step: int
    t: float
    kind: str
    value: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"step": int(self.step), "t": round(float(self.t), 4),
                "kind": self.kind, "value": _f(self.value)}


@dataclass
class MetaSegment:
    """One ALNS adaptation step: the weights as they stood after the update,
    and the usage and scores that produced them."""
    step: int
    t: float
    destroy_weights: List[float]
    repair_weights: List[float]
    destroy_used: List[int]
    repair_used: List[int]
    destroy_scores: List[float]
    repair_scores: List[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": int(self.step), "t": round(float(self.t), 4),
            "dw": [_f(v) for v in self.destroy_weights],
            "rw": [_f(v) for v in self.repair_weights],
            "du": [int(v) for v in self.destroy_used],
            "ru": [int(v) for v in self.repair_used],
            "ds": [_f(v) for v in self.destroy_scores],
            "rs": [_f(v) for v in self.repair_scores],
        }


@dataclass
class MetaTrace:
    """A recorded metaheuristic run."""
    method: str = ""
    samples: List[MetaSample] = field(default_factory=list)
    events: List[MetaEvent] = field(default_factory=list)
    segments: List[MetaSegment] = field(default_factory=list)
    stride: int = 1
    max_samples: int = 3000
    steps: int = 0                       # total steps the search actually took
    destroy_ops: List[str] = field(default_factory=list)
    repair_ops: List[str] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method": self.method,
            "samples": [s.to_dict() for s in self.samples],
            "events": [e.to_dict() for e in self.events],
            "segments": [s.to_dict() for s in self.segments],
            "stride": int(self.stride),
            "max_samples": int(self.max_samples),
            "steps": int(self.steps),
            "destroy_ops": list(self.destroy_ops),
            "repair_ops": list(self.repair_ops),
            "params": dict(self.params),
        }


class MetaTracer:
    """Collects a `MetaTrace` while a search runs.

    Call `add` once per step; it decides on its own whether this step is on the
    stride. `event` records something that must never be dropped.
    """

    def __init__(self, method: str, max_samples: int = 3000,
                 params: Optional[Dict[str, Any]] = None):
        self.trace = MetaTrace(method=method, max_samples=max(2, int(max_samples)),
                               params=dict(params or {}))
        self._stride = 1
        self._next = 0

    # -- recording ---------------------------------------------------------
    def add(self, sample: MetaSample) -> None:
        self.trace.steps = max(self.trace.steps, sample.step + 1)
        if sample.step < self._next:
            return
        self._next = sample.step + self._stride
        self.trace.samples.append(sample)
        if len(self.trace.samples) >= self.trace.max_samples:
            self._decimate()

    def _decimate(self) -> None:
        """Halve the buffer and double the stride.

        Keeping every second sample preserves uniform coverage of the whole run
        so far, which is the property a convergence curve needs; keeping a
        prefix instead would show the first seconds of the search and nothing
        after them.
        """
        self.trace.samples = self.trace.samples[::2]
        self._stride *= 2
        self.trace.stride = self._stride
        if self.trace.samples:
            self._next = self.trace.samples[-1].step + self._stride

    def event(self, step: int, t: float, kind: str,
              value: Optional[float] = None) -> None:
        self.trace.events.append(MetaEvent(step=step, t=t, kind=kind, value=value))

    def segment(self, seg: MetaSegment) -> None:
        self.trace.segments.append(seg)

    # -- finishing ---------------------------------------------------------
    def finish(self, steps: int, last: Optional[MetaSample] = None) -> MetaTrace:
        """Close the trace. `last` is appended unconditionally so the curve
        always reaches the end of the run rather than stopping at the last
        point that happened to fall on the stride."""
        self.trace.steps = max(self.trace.steps, int(steps))
        if last is not None:
            if not self.trace.samples or self.trace.samples[-1].step != last.step:
                self.trace.samples.append(last)
        self.trace.stride = self._stride
        return self.trace
