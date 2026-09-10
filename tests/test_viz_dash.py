"""The convergence dashboard payload (roadmap §2.4).

`tests/test_meta_trace.py` proves the traces are faithful records of the
searches. These tests cover the payload built on top of them, and in particular
the two things this view could most easily get wrong:

* **the shared axis.** Three methods are drawn on one chart, so the limits have
  to contain every series or a curve silently leaves the plot.
* **the reference floor.** It is drawn as the thing the methods are being judged
  against, so it must never be an unproven incumbent presented as a bound.
"""
from __future__ import annotations

import json
import math

import pytest

from drp.exact.bnb import solve_bnb
from drp.instances import generate_instance
from drp.meta.alns import solve_alns
from drp.meta.construct import best_construction
from drp.meta.ga import solve_ga
from drp.meta.sa import solve_sa
from drp.viz.dashdata import (METHOD_COLOR, STEP_LABEL, MethodRun,
                              build_dashboard_data)
from drp.viz.webdash import DATA_TOKEN, NAME_TOKEN, render_dashboard_html

LONG_CLOCK = 600.0


def _inst():
    return generate_instance("dash", 12, 4, seed=7)


def _runs(inst, seed=1):
    ga = solve_ga(inst, seed=seed, generations=30, time_limit=LONG_CLOCK, trace=True)
    sa = solve_sa(inst, seed=seed, max_iter=800, time_limit=LONG_CLOCK, trace=True)
    al = solve_alns(inst, seed=seed, max_iter=800, time_limit=LONG_CLOCK, trace=True)
    return [
        MethodRun("ga", ga.trace, ga.best_energy, ga.time, seed, solution=ga.best_solution),
        MethodRun("sa", sa.trace, sa.best_energy, sa.time, seed, solution=sa.best_solution),
        MethodRun("alns", al.trace, al.best_energy, al.time, seed, solution=al.best_solution),
    ]


# ---------------------------------------------------------------------------
def test_build_dashboard_data_refuses_an_untraced_run():
    inst = _inst()
    r = solve_sa(inst, seed=1, max_iter=200, time_limit=LONG_CLOCK)
    assert r.trace is None
    with pytest.raises(ValueError, match="trace"):
        build_dashboard_data(inst, [MethodRun("sa", r.trace, r.best_energy, r.time, 1)])


def test_build_dashboard_data_refuses_an_empty_run_list():
    with pytest.raises(ValueError, match="at least one"):
        build_dashboard_data(_inst(), [])


def test_axis_limits_contain_every_series():
    """Three methods share one chart. A limit that does not contain a series
    would drop that curve off the plot with no warning."""
    inst = _inst()
    runs = _runs(inst)
    d = build_dashboard_data(inst, runs)
    m = d["meta"]

    for run in runs:
        for s in run.trace.samples:
            assert s.t <= m["t_max"] + 1e-9
            assert s.step <= m["step_max"]
            for v in (s.best, s.current, s.mean):
                if v is not None and math.isfinite(v):
                    assert m["e_lo"] - 1e-6 <= v <= m["e_hi"] + 1e-6
    assert m["t_max"] > 0 and m["step_max"] > 0
    assert m["e_hi"] > m["e_lo"]


def test_each_method_keeps_its_own_identity():
    inst = _inst()
    d = build_dashboard_data(inst, _runs(inst))
    assert [m["method"] for m in d["methods"]] == ["ga", "sa", "alns"]
    seen = set()
    for m in d["methods"]:
        assert m["color"] == METHOD_COLOR[m["method"]]
        assert m["color"] not in seen, "two methods share a colour"
        seen.add(m["color"])
        # one step is not one step across methods, and the label must say which
        assert m["step_label"] == STEP_LABEL[m["method"]]
        assert m["trace"]["method"] == m["method"]
    assert d["methods"][0]["step_label"] == "generation"
    assert d["methods"][1]["step_label"] == "iteration"


def test_reported_best_matches_the_trace_and_the_solution():
    """Three numbers that must agree: what the solver returned, where its trace
    ends, and what the attached solution actually costs."""
    from drp.core.energy import total_energy

    inst = _inst()
    runs = _runs(inst)
    d = build_dashboard_data(inst, runs)
    for run, m in zip(runs, d["methods"]):
        assert m["best_energy"] == pytest.approx(run.best_energy, rel=1e-12)
        assert run.trace.samples[-1].best == pytest.approx(run.best_energy, rel=1e-12)
        assert total_energy(inst, run.solution) == pytest.approx(run.best_energy,
                                                                 rel=1e-9)
        assert m["solution"]["routes"]


def test_best_overall_is_the_best_of_the_runs():
    inst = _inst()
    runs = _runs(inst)
    d = build_dashboard_data(inst, runs)
    assert d["meta"]["best_overall"] == pytest.approx(
        min(r.best_energy for r in runs), rel=1e-12)


def test_a_reference_floor_is_included_in_the_limits():
    """The floor is drawn across the chart, so it has to be inside the vertical
    range the page is told about."""
    inst = _inst()
    d = build_dashboard_data(inst, _runs(inst), reference=1.0,
                             reference_label="silly floor")
    assert d["reference"] == 1.0
    assert d["reference_label"] == "silly floor"
    assert d["meta"]["e_lo"] <= 1.0


def test_a_proven_optimum_really_does_floor_every_method():
    """The point of drawing a reference: if B&B proved an optimum, no
    metaheuristic may be below it. A violation would mean one of them is
    reporting an energy it cannot actually achieve."""
    inst = generate_instance("small", 8, 3, seed=21)
    b = solve_bnb(inst, time_limit=120.0, warm_start=best_construction(inst))
    assert b.optimal, "pick an instance B&B can finish"

    runs = _runs(inst)
    d = build_dashboard_data(inst, runs, reference=b.best_energy,
                             reference_label="B&B optimum")
    for m in d["methods"]:
        assert m["best_energy"] >= b.best_energy - 1e-6, \
            f"{m['method']} claims {m['best_energy']} below the proven optimum"
    assert d["meta"]["e_lo"] <= b.best_energy


def test_payload_is_json_safe():
    inst = _inst()
    d = build_dashboard_data(inst, _runs(inst), reference=100.0)
    text = json.dumps(d, allow_nan=False)
    assert "Infinity" not in text and "NaN" not in text


def test_render_dashboard_html_substitutes_both_placeholders(tmp_path):
    inst = _inst()
    out = render_dashboard_html(inst, _runs(inst), tmp_path / "sub" / "dash.html",
                                reference=900.0, reference_label="B&B optimum")
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert DATA_TOKEN not in text
    assert NAME_TOKEN not in text
    assert "<script" in text
    assert '"name": "dash"' in text
    assert '"method": "alns"' in text
    assert out.stat().st_size > 20_000


def test_render_dashboard_html_with_a_single_method(tmp_path):
    """The page must not assume three panels."""
    inst = _inst()
    sa = solve_sa(inst, seed=1, max_iter=300, time_limit=LONG_CLOCK, trace=True)
    out = render_dashboard_html(
        inst, [MethodRun("sa", sa.trace, sa.best_energy, sa.time, 1)],
        tmp_path / "one.html")
    assert out.stat().st_size > 20_000
    assert '"method": "sa"' in out.read_text(encoding="utf-8")


def test_alns_operator_names_reach_the_payload():
    """The dashboard labels the operator-share chart from these; an empty list
    would leave the one genuinely new ALNS view unlabelled."""
    inst = _inst()
    al = solve_alns(inst, seed=1, max_iter=600, time_limit=LONG_CLOCK,
                    segment=100, trace=True)
    d = build_dashboard_data(
        inst, [MethodRun("alns", al.trace, al.best_energy, al.time, 1)])
    t = d["methods"][0]["trace"]
    assert t["destroy_ops"] and t["repair_ops"]
    assert t["segments"]
    for seg in t["segments"]:
        assert len(seg["dw"]) == len(t["destroy_ops"])
        assert len(seg["rw"]) == len(t["repair_ops"])
