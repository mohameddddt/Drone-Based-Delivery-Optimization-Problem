"""Metaheuristic search traces (roadmap §2.4, convergence dashboards).

Same standard as `tests/test_bnb_trace.py`: the trace is a claim about a search
that really happened, so it is tested as a claim rather than smoke-tested as a
data structure.

The invariance claim needs stating carefully, and these tests draw the line
where it actually falls. **For a fixed iteration/generation budget the trace
changes nothing** — it consumes no random numbers and takes no branch the search
can see, so the same solution, energy, history and counters come back. Under a
*wall-clock* limit that is not true and is not claimed: recording costs time, so
fewer iterations fit inside the budget, exactly as any other overhead would.
Every invariance test here therefore pins a fixed budget and a generous clock.
"""
from __future__ import annotations

import json
import math

import pytest

from drp.instances import generate_instance, generate_zone_instance
from drp.meta.alns import DESTROY_OPS, REPAIR_OPS, solve_alns
from drp.meta.ga import solve_ga
from drp.meta.sa import solve_sa
from drp.meta.trace import MetaSample, MetaTracer

# (callable, fixed-budget kwarg) — a budget small enough to be quick, large
# enough that the search actually adapts.
RUNNERS = [
    ("sa", solve_sa, {"max_iter": 900}),
    ("ga", solve_ga, {"generations": 40}),
    ("alns", solve_alns, {"max_iter": 900}),
]
LONG_CLOCK = 600.0


def _inst():
    return generate_instance("meta", 12, 4, seed=7)


def _run(fn, budget, **kw):
    return fn(_inst(), seed=kw.pop("seed", 1), time_limit=LONG_CLOCK, **budget, **kw)


# ---------------------------------------------------------------------------
# 1. tracing is opt-in and, at a fixed budget, free
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name,fn,budget", RUNNERS)
def test_tracing_is_off_by_default(name, fn, budget):
    res = _run(fn, budget)
    assert res.trace is None


@pytest.mark.parametrize("name,fn,budget", RUNNERS)
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_tracing_does_not_change_a_fixed_budget_search(name, fn, budget, seed):
    off = _run(fn, budget, seed=seed)
    on = _run(fn, budget, seed=seed, trace=True)

    assert on.best_energy == off.best_energy
    assert on.best_solution.routes == off.best_solution.routes
    assert on.history == off.history
    if name == "ga":
        assert on.generations == off.generations
    else:
        assert on.iterations == off.iterations
    if name == "sa":
        assert (on.accepted, on.accepted_uphill, on.reheats) == \
               (off.accepted, off.accepted_uphill, off.reheats)
    if name == "alns":
        assert on.destroy_weights == off.destroy_weights
        assert on.repair_weights == off.repair_weights


# ---------------------------------------------------------------------------
# 2. the trace is a faithful record
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name,fn,budget", RUNNERS)
def test_series_are_ordered_and_end_where_the_search_ended(name, fn, budget):
    res = _run(fn, budget, trace=True)
    tr = res.trace
    assert tr.method == name
    assert tr.samples

    prev_step, prev_t, prev_best = -1, -1.0, math.inf
    for s in tr.samples:
        assert s.step > prev_step, "steps must strictly increase"
        assert s.t >= prev_t - 1e-9, "elapsed time must not go backwards"
        assert s.best <= prev_best + 1e-9, "best-so-far must never worsen"
        assert s.best <= s.current + 1e-9, \
            "the best-so-far cannot be worse than the working solution"
        prev_step, prev_t, prev_best = s.step, s.t, s.best

    assert tr.samples[-1].best == pytest.approx(res.best_energy, rel=1e-12)
    assert tr.samples[-1].step == tr.steps - 1
    assert tr.steps == (res.generations if name == "ga" else res.iterations)


@pytest.mark.parametrize("name,fn,budget", RUNNERS)
def test_every_improvement_is_recorded_as_an_event(name, fn, budget):
    """The dashboard marks improvements. They must be the search's own, and no
    event may claim an improvement that the best-so-far series does not show."""
    res = _run(fn, budget, trace=True)
    tr = res.trace
    bests = [e for e in tr.events if e.kind == "new_best"]
    assert bests, "the search never improved; pick a harder budget"

    prev = math.inf
    for e in bests:
        assert e.value < prev - 1e-12, "an improvement must actually improve"
        prev = e.value
    assert bests[-1].value == pytest.approx(res.best_energy, rel=1e-12)
    # events are in chronological order and inside the run
    steps = [e.step for e in bests]
    assert steps == sorted(steps)
    assert all(0 <= st < tr.steps for st in steps)


def test_sa_temperature_falls_except_where_it_reheats():
    res = solve_sa(_inst(), seed=5, max_iter=3000, time_limit=LONG_CLOCK,
                   reheat_after=200, trace=True)
    tr = res.trace
    temps = [s.temperature for s in tr.samples]
    assert all(t is not None and t > 0 for t in temps)

    reheats = [e for e in tr.events if e.kind == "reheat"]
    assert len(reheats) == res.reheats
    if not reheats:
        pytest.skip("no reheat fired at this budget")

    # between reheats the schedule is monotone: every rise must sit next to one
    rise_steps = [tr.samples[i].step for i in range(1, len(tr.samples))
                  if temps[i] > temps[i - 1] + 1e-12]
    reheat_steps = [e.step for e in reheats]
    for st in rise_steps:
        assert any(abs(st - r) <= tr.stride + 1 for r in reheat_steps), \
            f"temperature rose at step {st} with no reheat near it"


def test_sa_accepted_flags_agree_with_the_reported_counters():
    """`accepted` on a sample is what the Metropolis test actually returned, so
    on an untruncated trace the flags must add up to `SAResult.accepted`."""
    res = solve_sa(_inst(), seed=4, max_iter=800, time_limit=LONG_CLOCK, trace=True)
    tr = res.trace
    assert tr.stride == 1, "this test needs an undecimated trace"
    accepted = sum(1 for s in tr.samples if s.accepted)
    # the closing sample repeats the last step, so drop a duplicate if present
    assert abs(accepted - res.accepted) <= 1, (accepted, res.accepted)


def test_ga_population_stats_bracket_the_best():
    res = solve_ga(_inst(), seed=3, generations=40, time_limit=LONG_CLOCK, trace=True)
    for s in res.trace.samples:
        assert s.mean is not None and s.spread is not None
        assert s.mean >= s.current - 1e-9, \
            "the population mean cannot beat its own best member"
        assert s.spread >= 0
        assert math.isfinite(s.mean) and math.isfinite(s.spread), \
            "an infeasible member must be excluded, not averaged in"


def test_ga_population_stats_survive_an_infeasible_population():
    """Split returns inf for a tour no fleet can serve. Those members must be
    counted out of the mean rather than swallowing it."""
    inst = generate_zone_instance("tight", 12, 2, seed=11, n_zones=3)
    res = solve_ga(inst, seed=1, generations=25, time_limit=LONG_CLOCK, trace=True)
    for s in res.trace.samples:
        if s.mean is not None:
            assert math.isfinite(s.mean)
    assert "n_feasible_last" in res.trace.params


def test_alns_segments_are_the_adaptation_the_solver_actually_did():
    res = solve_alns(_inst(), seed=2, max_iter=1200, time_limit=LONG_CLOCK,
                     segment=100, trace=True)
    tr = res.trace
    assert tr.destroy_ops == [n for n, _ in DESTROY_OPS]
    assert tr.repair_ops == [n for n, _ in REPAIR_OPS]
    assert tr.segments, "no weight update was recorded"

    for seg in tr.segments:
        assert len(seg.destroy_weights) == len(DESTROY_OPS)
        assert len(seg.repair_weights) == len(REPAIR_OPS)
        assert all(w >= 0.05 - 1e-12 for w in seg.destroy_weights), \
            "the solver floors weights at 0.05; the trace must show that floor"
        assert all(w >= 0.05 - 1e-12 for w in seg.repair_weights)
        # a segment draws exactly one destroy and one repair per iteration it ran
        assert sum(seg.destroy_used) == sum(seg.repair_used)
        assert sum(seg.destroy_used) <= 100
        assert all(u >= 0 for u in seg.destroy_used + seg.repair_used)
        assert all(sc >= 0 for sc in seg.destroy_scores + seg.repair_scores)

    # the final segment's weights are the ones the solver reports
    last = tr.segments[-1]
    assert [round(w, 3) for w in last.destroy_weights] == \
        list(res.destroy_weights.values())
    assert [round(w, 3) for w in last.repair_weights] == \
        list(res.repair_weights.values())


def test_alns_samples_name_operators_that_exist():
    res = solve_alns(_inst(), seed=2, max_iter=600, time_limit=LONG_CLOCK, trace=True)
    tr = res.trace
    for s in tr.samples:
        assert s.op_destroy is None or 0 <= s.op_destroy < len(DESTROY_OPS)
        assert s.op_repair is None or 0 <= s.op_repair < len(REPAIR_OPS)
    assert any(s.op_destroy is not None for s in tr.samples)


# ---------------------------------------------------------------------------
# 3. decimation keeps the whole run, not a prefix
# ---------------------------------------------------------------------------
def test_decimation_covers_the_whole_run_uniformly():
    """A convergence curve truncated to its first N points is the one useless
    shape: it shows the opening of the search and nothing after it. Decimation
    must keep uniform coverage instead."""
    res = solve_sa(_inst(), seed=1, max_iter=4000, time_limit=LONG_CLOCK,
                   trace=True, trace_max_samples=200)
    tr = res.trace
    assert len(tr.samples) <= 200
    assert tr.stride > 1 and (tr.stride & (tr.stride - 1)) == 0, \
        "stride doubles, so it is a power of two"
    # the last sample is at the end of the run, not 200 steps in
    assert tr.samples[-1].step == tr.steps - 1
    assert tr.steps == res.iterations

    # the interior is a uniform stride
    gaps = {tr.samples[i + 1].step - tr.samples[i].step
            for i in range(len(tr.samples) - 2)}
    assert len(gaps) == 1, f"coverage is not uniform: {sorted(gaps)}"


@pytest.mark.parametrize("name,fn,budget", RUNNERS)
def test_decimation_does_not_drop_improvements(name, fn, budget):
    """Events are recorded in full precisely so that decimation cannot lose
    one -- the improvement markers on the chart must survive any cap."""
    full = _run(fn, budget, trace=True)
    capped = _run(fn, budget, trace=True, trace_max_samples=16)
    a = [(e.step, e.value) for e in full.trace.events]
    b = [(e.step, e.value) for e in capped.trace.events]
    assert a == b
    assert len(capped.trace.samples) <= 16 + 1   # +1 for the closing sample


def test_tracer_decimation_is_uniform_in_isolation():
    tr = MetaTracer("unit", max_samples=8)
    for i in range(200):
        tr.add(MetaSample(step=i, t=i * 0.01, best=200 - i, current=200 - i))
    out = tr.finish(200)
    assert len(out.samples) <= 8
    steps = [s.step for s in out.samples]
    assert steps[0] == 0
    gaps = {steps[i + 1] - steps[i] for i in range(len(steps) - 1)}
    assert len(gaps) == 1 and gaps.pop() == out.stride


# ---------------------------------------------------------------------------
# 4. it crosses into a browser as JSON
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name,fn,budget", RUNNERS)
def test_trace_to_dict_is_json_safe(name, fn, budget):
    res = _run(fn, budget, trace=True)
    d = res.trace.to_dict()
    text = json.dumps(d, allow_nan=False)
    assert "Infinity" not in text and "NaN" not in text
    assert d["method"] == name
    assert d["steps"] == (res.generations if name == "ga" else res.iterations)
    assert len(d["samples"]) == len(res.trace.samples)


def test_trace_to_dict_reports_an_infinite_energy_as_null():
    """A search that never found a feasible solution has an infinite best, and
    JSON has no Infinity. It must serialise as null, not as a number."""
    tr = MetaTracer("unit", max_samples=8)
    tr.add(MetaSample(step=0, t=0.0, best=math.inf, current=math.inf))
    d = tr.finish(1).to_dict()
    assert d["samples"][0]["best"] is None
    assert d["samples"][0]["current"] is None
    json.dumps(d, allow_nan=False)
