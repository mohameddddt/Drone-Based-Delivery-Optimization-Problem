"""This project's objective, checked against 74 answers it had no hand in.

Every correctness test elsewhere in this repository is self-referential: the
package is compared against a brute force *written in the same package*, from
the same understanding of the problem. A shared misunderstanding -- of the
rounding convention, of which node is the depot, of how capacity is counted --
would pass all of them.

CVRPLIB's Augerat sets ship a ``.sol`` beside every ``.vrp``: an optimal
solution and its cost, produced by other people with other code. Scoring their
routes with `total_energy` and comparing to their number is therefore an
*external* check, and it is a sharp one -- an off-by-one in the customer
indexing, a rounded distance where the metric wants exact, or a depot leg
charged twice all move the total.

The files are not committed (they are third-party data). Fetch them into
``data/CVRPLIB/`` from http://vrp.galgos.inf.puc-rio.br and these tests stop
skipping.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from drp.core import is_feasible, total_energy
from drp.instances import (benchmark_directory, read_cvrplib,
                           read_cvrplib_solution, solution_path_for)

CVRPLIB_DIR = Path(__file__).resolve().parent.parent / "data" / "CVRPLIB"

pytestmark = pytest.mark.skipif(
    not CVRPLIB_DIR.exists(),
    reason="CVRPLIB instances not present under data/CVRPLIB/")


def _pairs():
    """Every ``.vrp`` under data/CVRPLIB that ships a published solution."""
    return [(f, s) for f in sorted(CVRPLIB_DIR.rglob("*.vrp"))
            if (s := solution_path_for(f)) is not None]


def test_the_benchmark_set_is_actually_there():
    pairs = _pairs()
    assert pairs, "no .vrp/.sol pairs found"
    assert len(pairs) >= 20, f"only {len(pairs)} instances -- is the set complete?"


@pytest.mark.parametrize("vrp,sol", _pairs(), ids=lambda p: Path(p).stem)
def test_published_optimum_reproduces_under_our_objective(vrp, sol):
    """Their routes, our arithmetic, their number."""
    inst = read_cvrplib(vrp).instance
    published = read_cvrplib_solution(sol)
    if published.cost is None:
        pytest.skip(f"{Path(sol).name} records no cost")

    ours = total_energy(inst, published.solution())
    assert ours == pytest.approx(published.cost, abs=1e-6), (
        f"{inst.name}: published {published.cost}, we score {ours}")


@pytest.mark.parametrize("vrp,sol", _pairs(), ids=lambda p: Path(p).stem)
def test_published_optimum_passes_our_feasibility_checker(vrp, sol):
    """A published optimum our checker rejects would mean the checker is wrong."""
    inst = read_cvrplib(vrp).instance
    ok, reason = is_feasible(inst, read_cvrplib_solution(sol).solution())
    assert ok, f"{inst.name}: {reason}"


def test_the_comment_header_and_the_sol_file_agree():
    """Two independent statements of the same optimum, in the same download."""
    checked = 0
    for vrp, sol in _pairs():
        imported = read_cvrplib(vrp)
        published = read_cvrplib_solution(sol)
        if imported.best_known is None or published.cost is None:
            continue
        checked += 1
        assert imported.best_known == pytest.approx(published.cost), (
            f"{imported.instance.name}: COMMENT says {imported.best_known}, "
            f".sol says {published.cost}")
    assert checked >= 20


def test_no_method_may_ever_beat_a_published_optimum():
    """The headline invariant, on instances with an externally proved optimum.

    Greedy construction is the cheap probe: if it ever came in *below* a
    published optimum, either the objective or the import is wrong. (Solvers are
    exercised against these instances in the study runs, not here -- this test
    has to stay fast.)
    """
    from drp.meta.construct import best_construction

    for imported in benchmark_directory(CVRPLIB_DIR, limit=12):
        sol_file = solution_path_for(imported.source)
        if sol_file is None:
            continue
        optimum = read_cvrplib_solution(sol_file).cost
        if optimum is None:
            continue
        sol = best_construction(imported.instance)
        assert sol is not None, f"{imported.instance.name}: no feasible construction"
        assert total_energy(imported.instance, sol) >= optimum - 1e-6
