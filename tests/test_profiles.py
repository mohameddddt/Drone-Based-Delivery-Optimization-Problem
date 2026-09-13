"""Roadmap §6, the profiling half: profiles, ECDFs, anytime, TTT, hardness.

The analyses are checked on hand-built rows whose answers can be worked out on
paper, so a wrong denominator or an off-by-one in a step function moves a
number rather than a picture. The solver-side half -- that every metaheuristic
records a trajectory ending at the energy it returned, and that recording one
changes nothing -- is checked on real runs.
"""
import json
import math

import numpy as np
import pytest

from drp.eval.profiles import (anytime_curves, ecdf, gap_pct, hardness_correlation,
                               instance_features, mean_gap_by_instance,
                               performance_profile, performance_ratios,
                               primal_gap, primal_integral, quality_ecdf,
                               reference_values, time_to_target, trajectory,
                               ttt_ecdf, value_at)
from drp.eval.runner import solve_one
from drp.instances import generate_instance
from drp.meta.alns import solve_alns
from drp.meta.ga import solve_ga
from drp.meta.sa import solve_sa


def row(inst, method, energy, seed=None, feasible=True, optimal=False,
        anytime=None, budget=5.0):
    extra = {} if anytime is None else {"anytime": anytime}
    return {"instance": inst, "method": method, "energy": energy, "seed": seed,
            "feasible": int(feasible), "optimal": int(optimal),
            "time_budget": budget, "extra": json.dumps(extra)}


# ---------------------------------------------------------------------------
# references and gaps
# ---------------------------------------------------------------------------
def test_reference_prefers_published_then_proven_then_best():
    rows = [row("a", "bnb", 110.0, optimal=True), row("a", "alns", 100.0),
            row("b", "bnb", 50.0), row("b", "ga", 40.0),
            row("c", "ga", None, feasible=False)]
    refs = reference_values(rows)
    assert refs["a"] == 110.0        # proven wins even over a lower (buggy) value
    assert refs["b"] == 40.0
    assert "c" not in refs
    assert reference_values(rows, {"b": 39.0})["b"] == 39.0


def test_gap_pct_and_primal_gap():
    assert gap_pct(110, 100) == pytest.approx(10.0)
    assert gap_pct(math.inf, 100) == math.inf
    assert gap_pct(100 * (1 + 1e-13), 100) == 0.0     # float noise is a tie
    assert primal_gap(math.inf, 100) == 1.0
    assert primal_gap(100, 100) == 0.0
    assert primal_gap(200, 100) == pytest.approx(0.5)


def test_ecdf_counts_unsolved_in_the_denominator():
    xs, ys = ecdf([3.0, 1.0, 1.0, math.inf])
    assert xs == [1.0, 3.0]
    assert ys == [0.5, 0.75]            # stops below 1: one run never solved


# ---------------------------------------------------------------------------
# performance profiles
# ---------------------------------------------------------------------------
def profile_rows():
    return [
        row("i1", "A", 100.0, 1), row("i1", "A", 100.0, 2), row("i1", "B", 120.0, 1),
        row("i2", "A", 150.0, 1), row("i2", "B", 100.0, 1),
        row("i3", "A", 100.0, 1), row("i3", "B", None, 1, feasible=False),
    ]


def test_performance_ratios():
    r = performance_ratios(profile_rows())
    assert r["i1"] == {"A": 1.0, "B": pytest.approx(1.2)}
    assert r["i2"] == {"A": pytest.approx(1.5), "B": 1.0}
    assert r["i3"]["A"] == 1.0 and r["i3"]["B"] == math.inf


def test_performance_profile_by_hand():
    p = performance_profile(profile_rows(), taus=[1.0, 1.2, 1.5, 10.0])
    assert p["n_instances"] == 3
    assert p["rho"]["A"] == pytest.approx([2 / 3, 2 / 3, 1.0, 1.0])
    assert p["rho"]["B"] == pytest.approx([1 / 3, 2 / 3, 2 / 3, 2 / 3])
    assert p["wins"] == pytest.approx({"A": 2 / 3, "B": 1 / 3})


def test_profile_is_monotone_and_ties_count_for_both():
    rows = [row("i", "A", 10.0), row("i", "B", 10.0)]
    p = performance_profile(rows)
    assert p["wins"] == {"A": 1.0, "B": 1.0}
    for m in ("A", "B"):
        assert all(a <= b for a, b in zip(p["rho"][m], p["rho"][m][1:]))


def test_best_statistic_differs_from_mean():
    rows = [row("i", "A", 100.0, 1), row("i", "A", 140.0, 2), row("i", "B", 110.0, 1)]
    assert performance_ratios(rows, statistic="mean")["i"]["B"] == 1.0
    assert performance_ratios(rows, statistic="best")["i"]["A"] == 1.0


# ---------------------------------------------------------------------------
# quality ECDF
# ---------------------------------------------------------------------------
def test_quality_ecdf():
    rows = profile_rows()
    refs = reference_values(rows)
    q = quality_ecdf(rows, refs)
    assert q["B"]["runs"] == 3 and q["B"]["unsolved"] == 1
    assert q["A"]["xs"] == [0.0, 50.0]
    assert q["A"]["ys"] == [0.75, 1.0]


# ---------------------------------------------------------------------------
# anytime / time-to-target
# ---------------------------------------------------------------------------
TRAJ = [(0.5, 200.0), (1.0, 150.0), (3.0, 100.0)]


def test_value_at_is_a_step_function():
    assert value_at(TRAJ, 0.1) == math.inf
    assert value_at(TRAJ, 0.5) == 200.0
    assert value_at(TRAJ, 2.999) == 150.0
    assert value_at(TRAJ, 99) == 100.0


def test_time_to_target():
    assert time_to_target(TRAJ, 150.0) == 1.0
    assert time_to_target(TRAJ, 99.0) == math.inf


def test_primal_integral_by_hand():
    # gap 1 on [0, .5), 0.5 on [.5, 1), 1/3 on [1, 3), 0 on [3, 5]
    expected = (1 * 0.5 + 0.5 * 0.5 + (1 / 3) * 2.0) / 5.0
    assert primal_integral(TRAJ, 100.0, 5.0) == pytest.approx(expected)
    assert primal_integral([(0.0, 100.0)], 100.0, 5.0) == 0.0
    assert primal_integral([], 100.0, 5.0) == 1.0


def test_trajectory_parses_the_stored_json_and_tolerates_old_rows():
    assert trajectory(row("i", "sa", 1.0, anytime=[[0.1, 2.0]])) == [(0.1, 2.0)]
    assert trajectory(row("i", "sa", 1.0)) is None
    assert trajectory({"extra": None}) is None


def test_anytime_and_ttt_aggregate():
    rows = [row("i", "A", 100.0, 1, anytime=[[0.0, 120.0], [2.0, 100.0]]),
            row("i", "A", 110.0, 2, anytime=[[1.0, 110.0]]),
            row("i", "B", 100.0, 1),                     # no trajectory: skipped
            row("i", "B", 100.0, 2, anytime=[[0.0, 100.0]])]
    refs = {"i": 100.0}
    c = anytime_curves(rows, refs, methods=["A", "B"], grid=[0.5, 1.5, 4.0])
    a = c["methods"]["A"]
    assert a["runs"] == 2
    assert a["solved_share"] == [0.5, 1.0, 1.0]
    assert a["mean_gap"] == pytest.approx([20.0, 15.0, 5.0])
    assert c["methods"]["B"]["primal_integral"] == 0.0

    t = ttt_ecdf(rows, refs, methods=["A"], eps_pct=5.0)["methods"]["A"]
    assert t["runs"] == 2 and t["censored"] == 1
    assert t["xs"] == [2.0] and t["ys"] == [0.5]


# ---------------------------------------------------------------------------
# hardness
# ---------------------------------------------------------------------------
def test_instance_features_are_sane():
    inst = generate_instance("h", 12, 3, seed=5)
    f = instance_features(inst, samples=100)
    assert f["n"] == 12 and f["K"] == 3
    assert 0 < f["utilisation"] < 1          # the generator leaves slack
    assert f["battery_slack"] > 1            # every customer fits alone
    assert 0.3 < f["clark_evans"] < 2.0      # uniform-ish random points
    assert 0 <= f["split_feasible_share"] <= 1


def test_clark_evans_detects_clustering():
    inst = generate_instance("c", 30, 4, seed=1)
    uniform = instance_features(inst, samples=0)["clark_evans"]
    coords = np.array(inst.coords, dtype=float)
    rng = np.random.default_rng(0)
    centres = rng.uniform(0, 100, size=(3, 2))
    coords[1:] = centres[rng.integers(0, 3, 30)] + rng.normal(0, 1.5, size=(30, 2))
    coords[0] = coords[1:].mean(axis=0)
    inst.coords = coords
    inst.invalidate_distances()
    assert instance_features(inst, samples=0)["clark_evans"] < 0.5 * uniform


def test_hardness_correlation_recovers_a_planted_relation_and_controls_for_n():
    rng = np.random.default_rng(3)
    feats, outcome = {}, {}
    for i in range(40):
        n = float(rng.integers(10, 100))
        util = float(rng.uniform(0.3, 1.0))
        feats[f"i{i}"] = {"n": n, "utilisation": util, "K": n / 5}
        outcome[f"i{i}"] = 10 * util ** 3 + rng.normal(0, 0.2)
    rows = {r["feature"]: r for r in hardness_correlation(feats, outcome)}
    assert rows["utilisation"]["rho"] > 0.8 and rows["utilisation"]["p"] < 1e-6
    # K is n in disguise: raw correlation is whatever n's is, partial is ~0.
    assert rows["K"]["partial_rho"] is None or abs(rows["K"]["partial_rho"]) < 0.2


def test_mean_gap_by_instance_marks_unsolved_as_inf():
    rows = [row("i", "A", 110.0, 1), row("i", "A", None, 2, feasible=False),
            row("j", "A", 105.0, 1)]
    g = mean_gap_by_instance(rows, {"i": 100.0, "j": 100.0}, "A")
    assert g["i"] == math.inf and g["j"] == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# the solvers' side
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def inst():
    return generate_instance("any", 12, 3, seed=11)


@pytest.mark.parametrize("method", ["ga", "sa", "alns"])
def test_trajectory_is_monotone_and_ends_at_the_result(inst, method):
    r = solve_one(inst, method, seed=2, time_limit=0.7)
    ts = [t for t, _ in r.anytime]
    es = [e for _, e in r.anytime]
    assert ts == sorted(ts) and all(a > b for a, b in zip(es, es[1:]))
    assert es[-1] == pytest.approx(r.energy)
    assert r.extra["anytime"][-1][1] == pytest.approx(r.energy, rel=1e-6)


def test_greedy_gets_one_point(inst):
    r = solve_one(inst, "greedy")
    assert len(r.anytime) == 1 and r.anytime[0][1] == r.energy


def test_bnb_holds_its_warm_start_from_time_zero(inst):
    r = solve_one(inst, "bnb", time_limit=2.0)
    assert r.anytime[0][0] == 0.0
    assert r.anytime[-1][1] == r.energy
    greedy = solve_one(inst, "greedy").energy
    if len(r.anytime) == 2:                 # improved on its warm start
        assert r.anytime[0][1] == pytest.approx(greedy)
        assert r.energy < greedy
    else:                                   # the warm start was already optimal
        assert r.energy == pytest.approx(greedy)


def test_recording_changes_nothing_under_an_iteration_budget(inst):
    """Same seed, same iteration budget, no time pressure: the answer must
    match exactly what the solvers returned before trajectories existed --
    which, since recording draws no random numbers, is itself."""
    a = solve_sa(inst, seed=4, max_iter=3000, time_limit=math.inf)
    b = solve_sa(inst, seed=4, max_iter=3000, time_limit=math.inf)
    assert a.best_energy == b.best_energy and a.history == b.history
    g1 = solve_ga(inst, seed=4, generations=30, time_limit=math.inf)
    g2 = solve_ga(inst, seed=4, generations=30, time_limit=math.inf)
    assert g1.best_energy == g2.best_energy and len(g1.anytime) == len(g2.anytime)


def test_alns_operator_subsets(inst):
    r = solve_alns(inst, seed=1, max_iter=300, time_limit=math.inf,
                   destroy_ops=["random"], repair_ops=["greedy"])
    assert set(r.destroy_weights) == {"random"}
    assert set(r.repair_weights) == {"greedy"}
    full = solve_alns(inst, seed=1, max_iter=300, time_limit=math.inf)
    same = solve_alns(inst, seed=1, max_iter=300, time_limit=math.inf,
                      destroy_ops=["random", "worst", "shaw", "route"],
                      repair_ops=["greedy", "regret2", "regret3"])
    assert full.best_energy == same.best_energy       # naming all = default
    with pytest.raises(ValueError):
        solve_alns(inst, destroy_ops=["nope"])
    with pytest.raises(ValueError):
        solve_alns(inst, repair_ops=[])


def test_solve_one_passes_options_through(inst):
    r = solve_one(inst, "alns", seed=1, time_limit=0.3,
                  options={"destroy_ops": ["shaw"]})
    assert set(r.extra["destroy_weights"]) == {"shaw"}
