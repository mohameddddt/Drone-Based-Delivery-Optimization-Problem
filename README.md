# Drone-Based Delivery Optimization

A capacitated drone routing problem where **energy depends on the weight still onboard**,
under battery, payload, fleet-size and no-fly constraints. Because a drone loads its whole
route at the depot and sheds weight at each delivery, the cost of a leg depends on *when*
in the route it is flown — which makes this genuinely order-dependent, not a relabelled
distance-VRP.

Ships with two mathematical formulations, an NP-hardness proof, an exact Branch & Bound
with an anytime dual bound, three metaheuristics, visibility-graph routing around polygonal
no-fly zones, a reproducible benchmark generator, an experiment harness, and 129 tests
including brute-force verification of the pieces everything else rests on.

```bash
pip install -e ".[dev]"

drp generate --n 20 --drones 5 --zones 3 --seed 7 -o city.json
drp solve city.json --method alns --time 30 -o plan.json
drp show plan.json --instance city.json -o routes.png --animate flight.gif
```

## Contents

- [Quick start](#quick-start) · [The model](#the-model) · [Methods](#methods)
- [Layout](#repository-layout) · [CLI](#command-line-interface) · [File formats](#file-formats)
- [Results](#results) · [Tests](#tests) · [Status & roadmap](#status)

## Quick start

```bash
pip install -e ".[dev]"      # or: pip install -r requirements.txt

python run_experiments.py    # full study  -> results/ + report tables (~20 min)
python generate_figures.py   # figures     -> results/fig_*.png
pytest -q -m "not slow"      # the fast test suite (~50 s)
```

For a one-minute smoke run instead of the full study:

```bash
python run_experiments.py --quick
```

The graded notebook still runs top to bottom on its own:

```bash
jupyter notebook "Van Der Linde_Code.ipynb"
```

## The model

Traversing an arc of length `d` carrying weight `w` costs

```
e(d, w) = d · (α + β·w)
```

with `α = 1` (the drone's own mass per unit distance) and `β = 0.3` — a fully loaded drone
uses ~30% more energy per unit distance than an empty one, consistent with the multirotor
literature (Dorling et al., *IEEE Trans. Transp. Electrif.* 3(4), 2017).

**Constraints.** Each customer served exactly once; at most `K` routes; per-route payload
`≤ Q` and energy `≤ B`; no forbidden arc flown.

**No-fly zones come in two flavours.** The original model marks individual arcs forbidden.
The better one — `--zones` — represents them as **polygons**, and a leg that would cross one
is *detoured around it* along the shortest obstacle-avoiding path, computed on a visibility
graph. That detour is folded into the distance matrix, so **every solver works unchanged**;
they simply see a cost structure that reflects real geography.

## Methods

| Method | Idea |
|---|---|
| **Greedy** | Nearest-neighbour and Clarke–Wright savings, both constraint-aware; cheaper one kept. Warm-starts everything else. |
| **Branch & Bound** | Depth-first over partitions into ordered routes, symmetry-broken by increasing first-customer index. Column-minimum lower bound. Reports a **valid anytime dual bound**, so a timed-out run still yields a real optimality gap. |
| **Genetic Algorithm** | Giant tour + Split DP. Tournament selection, Order Crossover, swap/2-opt mutation, elitism. |
| **Simulated Annealing** | Same encoding. Compound neighbourhood (2-opt / swap / or-move), geometric cooling, reheating on stagnation. |
| **ALNS** | Destroy (random / worst / Shaw / whole-route) + repair (greedy / regret-2 / regret-3) with adaptive operator weights, energy-aware insertion and noise. **Best average energy of any method.** |

All five share one implementation of the objective and the feasibility check, so the
comparison is fair by construction.

### The Split decoder

The GA, SA and ALNS all encode a solution as a permutation of customers with **no route
delimiters**, and a dynamic program cuts it into the energy-optimal set of `≤ K` feasible
routes. State `(i, k)` = "first `i` customers covered using exactly `k` routes"; the answer
is `min over k ≤ K of dp[n][k]`, so the fleet limit is enforced exactly rather than by
penalty.

This is the load-bearing design decision: crossover and mutation act on permutations and
are therefore *always valid*, and every feasibility question is answered inside Split. It
is also why `tests/test_split_optimality.py` brute-forces every segmentation and asserts
Split matches — if that claim were subtly false, all three metaheuristics would quietly
return worse answers and nothing else would notice.

### The anytime dual bound

A depth-first search cut off by its clock used to report only its incumbent — which,
warm-started from greedy, was often *still the greedy value*, with nothing to say about how
good it was. Branch & Bound now also reports a valid global lower bound:

```
drp solve city.json --method bnb --time 5
  energy   : 1504.69
  status   : timed out -- lower bound 288.40, gap 80.83%
```

Getting this right takes care. It is **not** enough to record the bound of the node you
happened to be in when time ran out: the unexplored space also contains every sibling not
yet reached. Each frame therefore materialises its children with their bounds before
descending, and contributes the ones it never entered to the frontier. The minimum over
that frontier is a true lower bound — asserted against brute force in
`tests/test_bnb_ground_truth.py`, including at 1 ms time limits.

The bound is weak (that column-minimum bound is why the search stalls near `n = 9`).
Strengthening it — Held–Karp 1-trees, LP relaxation, column generation — is roadmap §5.1.

## Repository layout

```
drp/
  core/        instance · solution · energy · feasibility
  geometry/    distance · nofly (polygons) · visibility (detour routing)
  instances/   generator · io (JSON formats) · schema/
  exact/       bnb (+ dual bound) · bounds · milp_flow (Formulation 2)
  meta/        encoding · split · construct · ga · sa · alns
  eval/        runner · store (SQLite) · metrics
  viz/         static · animate
  app/         cli
tests/         129 tests, incl. brute-force verification
report/        report.tex + generated tables
results/       runs.db, CSVs, figures
data/source/   the supplied last-mile coordinate dataset
notebooks/     data_instance_builder.ipynb
Van Der Linde_Code.ipynb    the graded submission, frozen
```

**The notebook is a frozen artefact.** The marks are in and its numbers appear in the
report, so it is left alone. `tests/test_notebook_parity.py` pins the proven optima and
greedy energies it produced, and fails if the package ever drifts from them.

## Command-line interface

```bash
drp generate --n 40 --drones 8 --zones 3 --seed 7 -o inst.json
drp solve    inst.json --method alns --time 60 --seed 1 -o sol.json
drp compare  inst.json --methods bnb,ga,sa,alns --seeds 1-10 --time 30
drp bench    --suite default --time 5 --seeds 1-5
drp show     sol.json --instance inst.json -o routes.png --animate flight.gif
drp export   sol.json --instance inst.json --format geojson -o routes.geojson
```

`drp` is installed by `pip install -e .`; `python -m drp.app` works without installing.

## File formats

Two documented JSON formats with schemas under `drp/instances/schema/`:

- **`drp-instance/v1`** — depot, customers, demands, fleet spec, energy parameters, and
  no-fly geometry (forbidden edges and/or polygons).
- **`drp-solution/v1`** — routes, per-leg energy and onboard weight, plus a **feasibility
  certificate** so a third party can check a claimed result without re-running a solver.

Solutions also export to GeoJSON and to a per-leg CSV manifest.

## Results

From the committed run — 12 instances, 5 seeds per metaheuristic, 20 s for B&B and 5 s per
metaheuristic seed. Full per-instance table in [PROGRESS.md](PROGRESS.md).

| Method | Avg. energy | Avg. time (s) | Optima found | Avg. gap on proven |
|---|---|---|---|---|
| **ALNS** | **1027.7** | 24.96 | 5/5 | 0.000% |
| Genetic Algorithm | 1047.7 | 24.11 | 5/5 | 0.000% |
| Simulated Annealing | 1103.7 | 25.00 | 5/5 | 0.000% |
| Branch & Bound | 1191.7 | 12.07 | 5/5 | 0.000% |
| Greedy construction | 1232.1 | 0.00 | 0/5 | 14.220% |

- Branch & Bound **proves optimality on `n = 5…9`** and times out from `n = 10`, locating
  the exact/heuristic crossover at about `n = 9`.
- **All three metaheuristics find every proven optimum**, and none ever returns below one.
  That is the project's main correctness check: a heuristic beating a true optimum would
  mean the objective or the exact method is wrong.
- **ALNS has the best average energy**, winning outright on the three largest instances. GA
  edges it on two mid-size ones, so they are close; both clearly beat SA at scale.
- From `n = 15` up, B&B's *value* equals greedy's: it is returning its warm-start
  incumbent. It is not optimising badly, it has not finished — and the dual bound now says
  by how much (66–89% of the interval unproved, because the bound is weak).

Every number lives in `results/runs.db`, one row per run tagged with the git SHA that
produced it. The report `\input`s generated tables; nothing is typed by hand.

## Tests

```bash
pytest -q                  # everything (~2.5 min)
pytest -q -m "not slow"    # the fast subset CI runs on every push (~50 s)
```

129 tests. The ones that matter most:

| Test | What it proves |
|---|---|
| `test_split_optimality` | Split matches brute-force enumeration of **every** segmentation. The GA, SA and ALNS all rest on this. |
| `test_bnb_ground_truth` | B&B equals exhaustive enumeration; the lower bound never exceeds the true optimum. A bound that overestimates silently returns a **wrong answer labelled "proven optimal"** — nothing else would catch it. |
| `test_notebook_parity` | The package still reproduces the graded notebook's committed numbers. |
| `test_feasibility_fuzz` | `is_feasible` agrees with an independently written checker across thousands of random solutions. |
|  `test_cross_validation` | The commodity-flow MILP is a valid lower bound on B&B, and equals it when the battery is slack. |
| `test_metamorphic` | Reversing a route is free when `β = 0` and generally is not when `β > 0`; scaling coordinates scales energy. |
| `test_geometry` | Detours match a hand-computed shortest path around an obstacle; blocked legs get longer, not deleted. |

## Status

See **[PROGRESS.md](PROGRESS.md)** for what is done, what is verified, and what is not —
tracked against the project roadmap. In short: **P1 Foundation is complete**, along with
three of the six roadmap quick wins (ALNS, polygonal no-fly zones, the B&B dual bound) and
the results store. P2 interactive visualisation, P4 real geography, and P5 research
extensions are not started.

## Building the report

```bash
python run_experiments.py && python generate_figures.py
pdflatex -output-directory=report report/report.tex
```
