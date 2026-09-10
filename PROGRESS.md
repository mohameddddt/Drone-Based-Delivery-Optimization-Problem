# Project progress

Status of `main`, tracked against the project roadmap. Updated 2026-09-10.

## Where this stands

The graded submission is done and unchanged. This document tracks the work *after*
that — turning a 37-cell notebook into software other people can use.

**P1 Foundation is complete, and all six roadmap quick wins are done.** §5.1's stronger
B&B bound and §6's significance testing are now in too. §2.2's playback has been rebuilt
as an interactive GSAP web page, and then rebuilt again around a real pan/zoom map after a
browser-driven design review. **§3's data layer has now landed**: a scenario builder,
instances built from the supplied Pontianak coordinates, CVRPLIB/Solomon import and
QGroundControl mission export. P2's remaining pieces (B&B tree explorer, SA/GA dashboards,
SVG export), §3's networked half (address geocoding, OSM basemaps), the §7–8 service and
most of P5 are not started.

| Phase | Status |
|---|---|
| **P1 Foundation** | ✅ **Complete** — package, formats, CLI, tests, results store, CI |
| **P2 See it** | ◐ Partial — animated playback ✅ (GIF + pan/zoom GSAP flight-replay page); B&B tree explorer, SA/GA dashboards, SVG export ✗ |
| **P3 Mean it** | ◐ Partial — polygonal no-fly ✅, visibility detours ✅, ALNS ✅, dual gap ✅, stronger bound ✅, significance testing ✅; wind ✗, performance profiles/ablations ✗ |
| **P4 Use it** | ◐ Partial — scenario builder ✅, real geography ✅, CVRPLIB/Solomon import ✅, QGC mission export ✅; geocoding, OSM basemaps, REST service ✗ |
| **P5 Push it** | ✗ Not started |

### The six quick wins

| # | Quick win | Status |
|---|---|---|
| §2.2 | Animated route playback | ✅ `drp show --animate` (GIF) and `--web` (pan/zoom GSAP replay page) |
| §1.4 | Split-DP brute-force test | ✅ `tests/test_split_optimality.py` |
| §4.1 | Polygonal no-fly via visibility graph | ✅ `drp/geometry/visibility.py` |
| §5.2 | ALNS | ✅ `drp/meta/alns.py` |
| §5.1 | Report the B&B dual bound | ✅ `drp/exact/bnb.py` |
| §1.5 | Results store, de-hardcoded figures | ✅ `drp/eval/store.py` |

---

## P1 — Foundation ✅

### §1.1 Package extraction

The notebook is now a frozen artefact, and the code lives in a real package:

```
drp/core/  geometry/  instances/  exact/  meta/  eval/  viz/  app/
```

`notebook.ipynb`'s original 37 cells (sections 1–12) are byte-for-byte untouched — the
marks are in and its numbers appear in the report. `tests/test_notebook_parity.py` pins
the proven optima and greedy energies it produced and fails if the package drifts from
them. Sections 13–14 were appended (not inserted) after §5.1 and §6 landed, importing the
`drp` package to demonstrate the stronger bound and the significance testing directly,
with real executed output — the graded portion stays exactly as marked, and the notebook
stays current as the project's single narrative entry point.

### §1.2 Instance and solution formats

`drp-instance/v1` and `drp-solution/v1`, both plain JSON with JSON Schemas under
`drp/instances/schema/`. Instances carry depot, customers, demands, fleet spec, energy
parameters and no-fly geometry (edges *and* polygons). Solutions carry routes, per-leg
energy and onboard weight, and a **feasibility certificate** so a third party can verify a
claimed result without re-running a solver. GeoJSON and per-leg CSV export too, and
(since §3) QGroundControl `.plan` missions. A third format, `drp-scenario/v1`, describes
the *recipe* an instance is built from rather than the instance itself.

### §1.3 Command-line interface

`drp generate | build | import | solve | compare | bench | show | export`, all exercised in CI.

### §1.4 Tests

**216 tests.** The ones the roadmap called for specifically:

| Roadmap item | Where | What it proves |
|---|---|---|
| Golden tests | `test_energy.py` | Hand-computed energies. Includes the order-dependence that defines the model. |
| Metamorphic | `test_metamorphic.py` | Reversal is free at `β=0` and generally is not at `β>0`; scaling coordinates by `c` scales energy by `c`. |
| **Split optimality** | `test_split_optimality.py` | Brute-forces **every** segmentation for small tours; Split matches exactly. |
| **B&B ground truth** | `test_bnb_ground_truth.py` | Exhaustive enumeration of every partition-into-ordered-routes; B&B matches. |
| **Bound validity** | `test_bnb_ground_truth.py`, `test_bounds.py` | Neither bound ever exceeds the true optimum — checked against brute force, and (for the anytime dual bound) at 1 ms, 10 ms and 120 s limits. |
| **Bound dominance** | `test_bounds.py` | The assignment-relaxation bound is never looser than the column-minimum sum it sits alongside. |
| Cross-validation | `test_cross_validation.py` | F2 ≤ B&B optimum always; equal when the battery is slack. Now an assertion, not a printout. |
| Feasibility fuzzing | `test_feasibility_fuzz.py` | 2,400 random solutions judged identically by `is_feasible` and an independently written reference checker. |
| **Significance machinery** | `test_stats.py` | Nemenyi CD reproduces Demšar's published table exactly for `k = 2..10`; a synthetic consistently-better method is detected as significant, a method compared against itself is not; bootstrap CI brackets a known mean. |
| **Import fidelity** | `test_benchmark_import.py` | An imported CVRPLIB file is the same problem the literature solved: depot at node 0 wherever the file put it, rounded `EUC_2D` reproduced, energy at `β=0` equal to distance, and B&B proving the value the file declares. |
| **Geographic instances** | `test_geodata.py` | Reproducible from the untouched CSV and independent of row order; distances are haversine kilometres; every instance in the suite has a feasible solution. |
| **Scenario recipes** | `test_scenario.py` | A named place resolves to that district's centroid, declared demands survive, a mistyped key is refused, and a synthetic scenario reproduces `generate_instance` exactly. |
| **Mission export** | `test_qgc.py` | The waypoints are the solved route in the solved order; a planar instance cannot be exported without an anchor; the anchor's projection measures the right number of metres. |

Bound validity deserves its billing: a bound that overestimates prunes the branch holding
the optimum, and the search then reports a **wrong answer labelled "proven optimal"**.
Nothing else in the project would catch that.

### §1.5 Results store

`results/runs.db` — SQLite, append-only, one row per run with exactly the roadmap's
columns (`instance, method, seed, time_budget, energy, feasible, nodes, wall_time,
git_sha`) plus the dual bound and the optimality flag. Every table and figure reads from
it. `run_experiments.py --tables-only` rebuilds the report tables without re-solving.

### §1.7 CI

`.github/workflows/ci.yml` — fast tests on Python 3.10 and 3.12 on every push, plus a CLI
smoke test and the full experiment pipeline. The brute-force suite runs on `main`.

---

## Quick wins, in detail

### §5.1 Anytime dual bound

`drp solve inst.json --method bnb --time 5` now prints:

```
energy   : 1504.69
status   : timed out -- lower bound 288.40, gap 80.83%
```

**This was subtle enough to get wrong once.** My first implementation recorded the bound of
the node occupied when the clock expired — which is *not* a valid global bound, because the
unexplored space also contains every sibling not yet reached, and those may be cheaper. The
correct version materialises each frame's children with their bounds before descending, and
on unwinding contributes the ones it never entered. The minimum over that frontier is a
true lower bound. `test_reported_dual_bound_is_valid` asserts it against brute force.

### §5.1 Stronger bound: assignment relaxation

The bound above was *weak* by construction — a plain sum of each customer's cheapest
entering arc, chosen independently per customer. Nothing stops two customers from
"sharing" the same cheap predecessor in the bound even though a real route cannot reuse
an arc, and the bound barely grows with `n` as a result. That flatness was exactly why
B&B stalled near `n = 9`.

`drp/exact/bounds.py::assignment_completion_bound` replaces it with an assignment-relaxation
(AP) bound: every unassigned customer, the open route's current tail, and each drone still
available to start a fresh route are matched via the Hungarian algorithm (`scipy.optimize.
linear_sum_assignment`) into a globally consistent one-predecessor-one-successor structure.
It drops subtour elimination, capacity and battery — same as before — but it cannot
double-book an arc the way the column-minimum sum can, so it strictly dominates it
(`test_assignment_bound_dominates_column_min`). Per-node cost is O(m³) instead of O(1), so
`drp/exact/bnb.py` computes the cheap sum first and only calls the Hungarian solve on
children that survive it — expensive bound, cheap gate.

Measured on the twelve committed instances (20 s each, same seeds as the table below):

| | Old bound | New bound |
|---|---|---|
| `S6_n10_k3` nodes to prove optimal | 1,519,663 (9.0 s) | 428,850 (13.9 s) |
| `S6_n10_k3` proves optimal in 20 s? | ✗ (this is where the old ceiling sat) | ✅ |
| `S5_n9_k3` nodes to prove optimal | 195,022 | 36,945 |
| Unproved interval at `n = 25–30` | 86–89% | 72–73% |

The exact-solvable ceiling moves from `n ≈ 9` to `n ≈ 10` — one step, not a leap, because
the bound is still a relaxation with no subtour elimination. Held–Karp or the LP relaxation
of the flow formulation remain the path to a bigger jump and are still not done.

**A phantom-return bug this exposed.** Tightening the completion bound broke three ground-truth
tests: B&B reported "proven optimal" at an energy *above* the true brute-forced optimum on
`n = 7` — the exact failure mode this project treats as the most serious possible bug, a wrong
answer with a confident label. The cause pre-dated this bound and was latent in the original
one too, just never tight enough to trigger it: the "committed cost so far" for the *still-open*
route was computed with `route_energy`, which bakes in a return-to-depot leg from whichever
customer currently happens to be last. If the route goes on to take more customers, that leg is
never actually flown — it's replaced by a longer path through the rest of the route — so
charging it is phantom cost with no lower-bound justification. Once stacked on a genuinely tight
completion term, phantom-plus-completion could exceed the true remaining cost and prune the real
optimum. Fixed by adding `drp.core.energy.route_energy_open` (every real leg except the
not-yet-flown return) and using it for the open route's running total in the bound, while the
return leg is charged exactly once — either when a route genuinely closes, or as one of the
assignment bound's own candidate arcs. `tests/test_bounds.py` now checks this directly, and
`test_bnb_ground_truth.py` is what caught it in the first place.

### §4.1 Polygonal no-fly zones

A blocked edge is no longer deleted; the drone flies **around** the obstacle. Zones are
polygons; a leg crossing one is replaced by the shortest obstacle-avoiding path, computed
on a visibility graph (nodes = depot + customers + polygon vertices, edges = mutually
visible pairs) and folded into the distance matrix.

**No solver changed.** B&B, GA, SA and ALNS all work unmodified on zone instances — verified
end to end in `test_geometry.py`, along with a hand-computed detour around a unit square.

### §5.2 ALNS

Destroy (random / worst / Shaw / whole-route) + repair (greedy / regret-2 / regret-3) with
adaptive operator weights and annealing acceptance. It gives the best average energy of any
method (1027.7 vs the GA's 1047.7 and SA's 1103.7) and wins outright on the three largest
instances — while still recovering all five proven optima.

The roadmap expected it to "beat both current metaheuristics comfortably". *Comfortably* is
too strong: the GA still edges it on `M1_n12_k4` and `L1_n20_k5`, so the two are close and
the honest claim is that ALNS is the better of the pair on the largest instances. Both
clearly beat SA at scale.

**It took three fixes to get right, and the first study run caught it.** The initial
implementation found only 3 of 5 proven optima (1.20% average gap) while GA and SA found
all 5 — on `S4_n8_k3` it returned *exactly* the greedy value, having never improved in 25
seconds. Rather than report that as a curiosity, it was worth diagnosing:

1. **Deterministic repair.** Measured directly: 400 destroy-and-repair rounds produced only
   **4 distinct tours**. Greedy and regret insertion are deterministic given the remaining
   tour, so the search kept regenerating the same solutions. Fixed with the standard ALNS
   noise term (Ropke & Pisinger 2006): each candidate position is offset by
   `noise · max_distance · U(−1,1)`. → 4/5.

2. **Destroy range too narrow.** A percentage ceiling alone is far too tight when `n` is
   small — 40% of 8 is 3. Added an absolute floor of 2 (removing one customer and greedily
   reinserting it usually just puts it back) and let the ceiling reach 8, capped at `n − 1`.

3. **The repair optimised the wrong objective.** This was the real one. Insertion positions
   were scored by pure distance detour — which ignores the load-dependent energy that is
   the entire point of this problem. Because a drone loads its whole route at the depot,
   placing a customer later in a route means hauling its parcel across every leg before it.
   The cost function now charges `β · q_c · (distance already flown before the position)`
   alongside the detour. → **5/5 proven optima.**

Worth stating plainly: an exhaustive search over all 40,320 giant tours confirmed 670.5
*was* reachable on `S4`, and ALNS was running 7,256 iterations against SA's 14,479 — so
this was never iteration starvation. It was a search converging efficiently to the wrong
place, which is exactly the failure mode a "it's a metaheuristic, it's stochastic" shrug
would have hidden.

### §2.2 Animated playback

`drp show --animate flight.gif` renders the fleet on a shared clock — drones moving
simultaneously, batteries draining, trails building, and a **red flash when two drones pass
within the separation distance**. Nothing enforces separation yet (that is §4.5), so those
flashes are precisely the conflicts a deconfliction model would have to resolve.

### §2.2 Interactive web playback

`drp show sol.json --instance inst.json --web flight.html` renders the same story as a
single self-contained HTML file — open it directly in a browser, nothing to serve.

This has been through three passes. The first was a sci-fi mission-control HUD, rejected
as generic. The second built a grounded aviation-chart identity on top of it. The third
(driven by `drone_delivery_visualisation_gsap_brief.md`, and by inspecting the running page
in a browser rather than reasoning about the source) found that the second pass still read
as a diagram with icons on it, and rebuilt the map and interaction layers outright.

**What the third pass changed.**

- **The map is a map you can handle.** Drag to pan with release inertia, wheel-zoom toward
  the cursor, pinch on touch, `+`/`−`/reset controls, arrow keys and `0`. A live scale bar
  and coordinate readout track the camera, and the graticule picks "nice" intervals per
  zoom level. Stops, aircraft, the hub and place labels counter-scale so they hold a
  constant *screen* size while the terrain zooms; route strokes hold a constant screen
  weight the same way. This was the single biggest gap — the previous version's camera
  moved only when the code moved it, which is not what anyone expects from a map.
- **The basemap was redrawn, not decorated.** It had been a jittered street grid with
  building rectangles scattered on it, which at any zoom read as noise. It is now composed
  like an aeronautical sheet: a river with banks and bridges where arterials cross it,
  land-use polygons for built-up areas and parks, and a **radial + ring road network
  centred on the hub**, so the road layout itself says where the depot is. Streets and
  buildings are masked to dry, built-up land. District labels are placed with collision
  rejection, so two names can never overprint. Still seeded deterministically from the
  instance, so it stays reproducible.
- **Delivery stops became the content layer.** They were house glyphs indistinguishable
  from the building texture — genuinely invisible mid-flight, which is a serious failure
  for the one thing the problem is *about*. They are now numbered chart symbols pinned to
  their exact coordinate, with four legible states: pending → inbound (pulsing) →
  delivering (radial burst) → delivered (green, checked).
- **The timeline became an instrument.** One lane per drone showing its airborne span with
  its delivery ticks inside it, event diamonds embedded in the track, a NOW playhead,
  drag-anywhere scrubbing and keyboard seek. Seeking backwards un-fires events, so the
  replay stays a replay instead of an ever-growing tally.
- **The rail carries the solver's story**, not just the fleet's: objective, flown distance,
  drones used, battery/payload limits, separation minimum, certificate reason — beside a
  live event stream. Clicking a drone still dims the rest, frames its route, redraws its
  trail so you *discover* the path, and opens a "why this route" panel built from
  `certificate.routes[k]` and the per-leg trace, now also showing the straight-line vs
  flown distance and the resulting airspace detour cost.
- **Restricted zones** keep the magenta aeronautical convention, but the hatch skirt is
  clipped to the polygon interior (it used to fringe outside the boundary) and a zone
  pulses when an aircraft comes near it.
- A `Fleet sweep` button gives the page one signature move: pull back, brighten every
  route, redraw them from the hub outward, settle exactly home. Everything still respects
  `prefers-reduced-motion`, and the layout holds down to 430 px.

**Four real bugs the browser inspection surfaced**, none of which the Python-side tests
could have caught:

1. **Deliveries fired at the wrong moment.** The service distance came from summing
   `leg.distance`, but the aircraft flies `route_polyline`, which is *longer* whenever it
   detours around a no-fly zone. The marker therefore flipped to delivered before the drone
   arrived — precisely on the instances where the geometry matters most. Now read off the
   flown polyline by matching each customer's coordinate to its vertex.
2. **Six separation breaches at `d=0`.** Every drone departs the same point at the same
   instant, so the whole fleet is inside the separation minimum before it has flown
   anywhere. The page opened reporting six conflicts on a feasible, conflict-free solution.
   Separation is now assessed only once an aircraft has cleared a terminal-area radius —
   and that radius is **displayed in the solver panel** rather than quietly applied, since
   it is an assumption the model does not itself make. Predicted breaches on the sample
   instance: 0.
3. **The map painted over the rail.** `.map-panel` had `aspect-ratio` while its grid row
   stretched to the tallest item, so the *height* fed back into the *width*: once the event
   log grew past the map, the map widened and covered the manifest. The rail is now
   height-bound to the map and scrolls internally.
4. **A tween that never died.** `setDelivered` cleared the inbound pulse via
   `setApproaching(id, false)`, whose guard had already seen `delivered === true` and
   returned before killing the tween — leaving a ring expanding forever around every served
   stop. Plus: drone markers didn't re-scale when zooming while paused, because their
   transform was only written by the per-frame `render()`.

Python's only job is still producing one JSON payload (`drp/viz/webdata.py`) — **unchanged
across all three passes**, because every one of the above reads fields that payload already
had. All choreography lives in `drp/viz/web/playback_template.html`. That split is
deliberate: the search-visualisation work planned next (§2.4 — B&B tree, SA/GA dashboards)
will reuse the same data-in/choreography-out pattern once B&B/GA/SA get step-by-step trace
instrumentation.

Still deliberately absent: **Solver Vision** (candidate routes considered and rejected),
which the brief asks for and which would be the most persuasive feature on the page. B&B,
GA and SA do not expose intermediate search states, and the brief's own rule — do not
fabricate what the solver does not produce — makes faking it the wrong move. It is blocked
on §2.4's trace instrumentation, not on the front end.

On coverage, stated plainly: `tests/test_viz_web.py` (6 tests) pins the **Python** side —
one flight per used route, cumulative distance agreeing with `route_energy`/`route_weight`,
detour-aware polylines, the separation default matching `animate_routes`, and placeholder
substitution. **There is still no browser test harness**, so none of the JavaScript above
is covered by CI; the four bugs listed were found by driving the page in Playwright by
hand. A headless smoke test of the rendered page is the obvious next hardening step.

Earlier correctness bug, still worth recording: several lookups (`rows[f.drone]`,
`DATA.flights[id]`, `DATA.solution.routes[id]`) originally assumed array index equals drone
id. That only holds when every drone has a non-empty route — `build_playback_data` lists
only *used* routes, so an idle drone partway through the fleet would silently misalign every
later drone's marker, telemetry row and "why this route" panel. Fixed by looking up
everywhere via the real `drone` field.

---

## P4 — Use it: the data layer (§3)

Everything above this line was measured on instances the project generated for itself, and
every solution it produced left as a PNG or a JSON file only this repository understands.
§3 is the section that connects it to data other people already have. Four of its pieces
landed on this branch; two did not, and the reason is stated below rather than implied.

### §3.1 Scenario builder

An instance is a *result* — coordinates, demands, a calibrated battery. A **scenario** is
the recipe that produced it, and that is the thing anyone actually wants to edit:

```json
{
  "schema": "drp-scenario/v1",
  "seed": 7,
  "source": {"district": "Pontianak South", "road_slot": "IV", "count": 20},
  "depot": {"place": "Pontianak South"},
  "fleet": {"n_drones": 5},
  "nofly": {"circles": [{"centre": {"place": "Pontianak City"}, "radius_km": 0.8}]}
}
```

`drp build scenario.json -o inst.json` turns that into an ordinary `drp-instance/v1` file,
so **nothing downstream learns about scenarios** — the solvers, the store, the figures and
the web playback all see what they always saw. `drp build --example` writes the file above
to start from. Three source kinds are supported: sample the real dataset, list points
outright (a hand-built what-if), or fall through to the original synthetic generator, which
`test_scenario.py` pins against `generate_instance` coordinate-for-coordinate.

Two deliberate hard edges:

- **A mistyped key is an error, not a default.** `"flete": {"n_drones": 3}` silently
  ignored would mean a study running with a different fleet than its own recipe claims.
  Unknown keys are rejected and named.
- **A zone drawn over a node is refused.** Centring a restricted circle on the same place
  as the depot — an easy thing to write — used to produce an instance whose depot row was
  entirely infinite, so every solver correctly reported "no feasible solution" and nobody
  could tell why. It now fails immediately, naming the node.

### §3.2 Real geography

`data/source/Last_Mile_Delivery_Coordinates.csv` — 4,360 real delivery points across the
six districts of Pontianak — had been sitting in the repository unused by anything the
solvers ran on. `drp/instances/geodata.py` wires it in: coordinates are `(lat, lon)`,
instances are built with `geodesic=True`, and distances are **haversine kilometres**.
Nothing downstream needed changing; only the units of the numbers did.

- **Selection is deterministic and the source file is never touched.** Points are sorted
  into a canonical order *before* sampling, so the instance does not depend on the order
  rows happen to arrive in — `test_geodata.py` checks that by shuffling the pool and
  demanding the same twelve points back.
- **The battery is calibrated, not guessed.** The nearest-neighbour rule the synthetic
  generator uses was extracted as `calibrate_battery` and is now shared verbatim by both
  families, so a geographic instance is neither infeasible nor trivially loose. Every
  instance in the suite is asserted to have a feasible construction.
- `geo_benchmark_suite()` is twelve instances whose `(n, K)` sizes **mirror
  `BENCHMARK_SPECS` exactly**, drawn from all six districts, so a geographic result can be
  read directly next to its synthetic counterpart.

#### The geographic pilot run

`drp bench --suite geo --seeds 1-3 --time 3 --bnb-time 10`, stored in
`results/geo_runs.db` as group `run_20260910_180619`. **This is a pilot, not a study**: 3
seeds and 3 s per metaheuristic seed against the committed run's 5 and 5, and a 10 s B&B
budget against 20 s. Energies are in kilometre-scaled units and are not comparable to the
synthetic table's numbers — only the shape of the result is.

| Instance | n | K | Greedy | B&B | GA | SA | ALNS | Proved? | Unproved interval |
|---|---|---|---|---|---|---|---|---|---|
| P1_n5_k2 | 5 | 2 | **6.10** | **6.10** | **6.10** | **6.10** | **6.10** | ✓ | 0.0% |
| P2_n6_k2 | 6 | 2 | 30.10 | **25.00** | **25.00** | **25.00** | **25.00** | ✓ | 0.0% |
| P3_n7_k2 | 7 | 3 | 20.90 | **17.50** | **17.50** | **17.50** | **17.50** | ✓ | 0.0% |
| P4_n8_k3 | 8 | 3 | 11.70 | **11.20** | **11.20** | **11.20** | **11.20** | ✓ | 0.0% |
| P5_n9_k3 | 9 | 3 | 20.40 | **18.60** | **18.60** | **18.60** | **18.60** | ✓ | 0.0% |
| P6_n10_k3 | 10 | 3 | 21.10 | **18.00** | **18.00** | **18.00** | **18.00** | ✓ | 0.0% |
| P7_n12_k4 | 12 | 4 | 23.00 | 23.00 | 23.00 | 23.00 | 23.00 | | 51.7% |
| P8_n15_k4 | 15 | 4 | 54.50 | 48.40 | 47.00 | 52.40 | **46.70** | | 50.8% |
| P9_n18_k5 | 18 | 5 | 29.00 | 29.00 | 26.80 | 29.00 | **25.70** | | 61.4% |
| P10_n20_k5 | 20 | 5 | 42.40 | 42.40 | **39.60** | 42.40 | 39.80 | | 67.3% |
| P11_n25_k6 | 25 | 6 | 33.60 | 33.60 | 31.20 | 33.40 | **29.70** | | 60.1% |
| P12_n30_k6 | 30 | 6 | 58.20 | 58.20 | 50.60 | 53.60 | **49.20** | | 72.6% |

| Method | Avg. energy | Avg. time (s) | Optima found | Avg. gap on proven |
|---|---|---|---|---|
| **ALNS** | **25.9** | 9.01 | 6/6 | 0.000% |
| Genetic Algorithm | 26.2 | 8.97 | 6/6 | 0.000% |
| Simulated Annealing | 27.5 | 9.00 | 6/6 | 0.000% |
| Branch & Bound | 27.6 | 5.61 | 6/6 | 0.000% |
| Greedy construction | 29.2 | 0.00 | 1/6 | 11.865% |

What the real geography changes, and what it does not:

- **The exact/heuristic crossover is in the same place.** B&B proves `n = 5…10` and times
  out from `n = 12`, on half the time budget the synthetic run gave it. Clustering did not
  move the ceiling; the missing subtour elimination in the bound is still what sets it.
- **The method ordering is unchanged** — ALNS, then GA, then SA, then timed-out B&B, then
  greedy — and no metaheuristic ever returns below a proven optimum.
- **Simulated annealing is the one that suffers.** On `P7`, `P9` and `P10` it returns
  *exactly* its warm-start value, having never improved; on the uniform synthetic suite it
  always improved. Clustered stops make a swap-and-reverse neighbourhood much likelier to
  land on an infeasible or plainly worse solution, and SA has no repair operator to
  recover. This is the clearest thing the real geography has told us that a uniform square
  could not — with the caveat that the pilot's 3 s budget is shorter than the committed
  run's 5 s.
- **The GA/ALNS pair separates here, and it is worth being careful about.** Paired Wilcoxon
  over the twelve instances gives ALNS better than GA at `p = 0.016`, where the synthetic
  suite could not distinguish them at all (`p ≥ 0.14`). But the Friedman post-hoc, which
  corrects for comparing five methods at once, does **not**: average ranks 1.88 (ALNS) and
  2.62 (GA) differ by 0.74, well inside the Nemenyi critical difference of 1.761. The
  honest reading is that the clustered instances *discriminate better* than uniform ones —
  a reason to expect the literature-instance import to pay off — not that ALNS is now
  proven better than the GA.
- `P7_n12_k4` is a curiosity: every method, including greedy, returns 23.00 and B&B cannot
  prove it (51.7% interval). Either the instance's calibrated battery leaves very few
  feasible shapes, or all four searches share the same basin. Not diagnosed.

### §3.3 CVRPLIB and Solomon import

`drp import` reads TSPLIB-style `.vrp` files and Solomon VRPTW files. What makes this worth
having is not the parsing but the **faithfulness**, and the module is explicit about it:

| | Choice | Why |
|---|---|---|
| Objective | `beta = 0` by default | With no load term, route energy *is* route distance, so the imported CVRP is the published problem and its optimum is a meaningful target. `--beta 0.3` gives a drone instance on benchmark geography, comparable to nothing published — and the import says so in its `dropped` list. |
| Metric | rounded `EUC_2D` | CVRPLIB optima are defined on integer-rounded distances. `round_distances` is a new instance field (and schema property) rather than a fudge at read time, so it survives the JSON round-trip. |
| Range | unbounded battery | A battery cap is not part of CVRP. |
| Solomon | time windows **dropped** | This model has no time dimension (§4.4). They are parsed and handed back on the `ImportedInstance` so nothing is lost, but a Solomon import is a *relaxation*: its optimum is a lower bound on the VRPTW optimum, not a target to match. |
| Solomon fleet | capacity bound + 1, capped at declared | The files declare 25 vehicles for 25 customers. Taken literally that is one drone per customer and the partitioning decision becomes vacuous. |

`tests/data/toy-n8-k3.vrp` is a hand-written fixture, and the test that matters asserts
that importing it and running B&B lands exactly on the optimum recorded in its `COMMENT` —
so getting the depot, the demands, the capacity or the metric wrong shows up as a moved
number rather than as a plausible one. **That value was proved by this repository's own
B&B and the fixture's comment says so**; it is not a published figure.

**What this does not yet deliver.** No third-party benchmark files are committed — they are
other people's data — so CI exercises the parsers on fixtures, not on Augerat or Uchoa.
The statistical-power argument in the closing section (a larger instance set is what would
separate GA, SA and ALNS) is now *unblocked*, not *done*: it needs someone to download a
set and run it.

### §3.5 QGroundControl mission export

`drp export --format qgc` writes one `.plan` per flying drone: take off at the depot, each
stop in the solved order with a hold for the drop, return, land. Polygonal no-fly zones
become **exclusion geofence polygons**, which is the closest the format comes to the
constraint the solver respected.

- A geodesic instance exports as it stands. A **planar instance refuses to export without
  an `--anchor lat,lon[,metres_per_unit]`**, because its coordinates mean nothing on Earth
  and inventing a location is worse than failing.
- The format carries no payload, no battery and no energy model, so the command prints a
  `mission_summary` of exactly those numbers beside the files it wrote — the flight plan
  and the optimisation result can then be reconciled by hand.
- **Not verified in QGroundControl itself.** There is no ground station on this machine.
  The files match the documented `.plan` schema and parse as JSON, and the tests check the
  command sequence, the waypoint order and the anchor's metre-scale projection against
  haversine — but nobody has loaded one into QGC.

### Deliberately not done: geocoding and OSM basemaps

Both need network access, which this environment does not have, and a stub that pretends
otherwise would be worse than an absence. What *is* there is a **gazetteer** — district
names resolved to their own centroids, computed from the dataset — which is what a scenario
file needs to say "put the depot in Pontianak South". The code labels it as such rather
than calling it geocoding.

### A geometry bug this surfaced

Building a scenario test — depot at a corner, a restricted circle in the middle, customers
at the other corners — produced a distance matrix in which the diagonal leg **flew straight
through the zone**. `segment_blocked` tested for a *proper* crossing with each polygon edge
and then sampled the whole segment's midpoint. A chord that enters and leaves through two
**vertices** crosses no edge properly, and if its midpoint happens to lie beyond the far
vertex the zone was judged clear. A symmetric layout produces exactly that alignment.

It is now cut at every point where it meets the boundary, and each piece classified by its
own midpoint. **No committed number moves**: the default suite has no polygons at all, and
re-computing all six zone instances' distance matrices under both the old and the new test
gives identical matrices to floating-point equality — this needs a degenerate alignment
that random coordinates essentially never produce, which is why it survived §4.1's tests.

---

## The committed run

12 instances, 5 seeds per metaheuristic, 20 s for B&B and 5 s per metaheuristic seed.
Wall clock 942 s. Stored in `results/runs.db` as group `run_20260909_221514` (superseding
`run_20260909_211828`, re-run after §5.1's assignment-relaxation bound landed — only the
B&B column moves; GA/SA/ALNS/Greedy differ from the previous run only by the ordinary
seed-vs-wall-clock noise of a time-boxed search).

| Instance | n | K | Greedy | B&B | GA | SA | ALNS | Proved? |
|---|---|---|---|---|---|---|---|---|
| S1_n5_k2 | 5 | 2 | 567.3 | **452.5** | **452.5** | **452.5** | **452.5** | ✓ |
| S2_n6_k2 | 6 | 2 | 624.8 | **592.5** | **592.5** | **592.5** | **592.5** | ✓ |
| S3_n7_k2 | 7 | 3 | 639.3 | **568.5** | **568.5** | **568.5** | **568.5** | ✓ |
| S4_n8_k3 | 8 | 3 | 691.5 | **670.5** | **670.5** | **670.5** | **670.5** | ✓ |
| S5_n9_k3 | 9 | 3 | 740.3 | **593.7** | **593.7** | **593.7** | **593.7** | ✓ |
| S6_n10_k3 | 10 | 3 | 925.1 | **839.5** | **839.5** | **839.5** | **839.5** | ✓ |
| M1_n12_k4 | 12 | 4 | 1035.7 | 984.3 | **922.1** | **922.1** | 930.0 | |
| M2_n15_k4 | 15 | 4 | 1316.1 | 1100.3 | **1011.2** | **1011.2** | **1011.2** | |
| M3_n18_k5 | 18 | 5 | 1564.5 | 1564.5 | 1292.5 | 1461.6 | **1281.9** | |
| L1_n20_k5 | 20 | 5 | 1830.5 | 1830.5 | **1428.3** | 1660.0 | 1451.1 | |
| L2_n25_k6 | 25 | 6 | 2122.1 | 2122.1 | 1702.4 | 1923.5 | **1686.2** | |
| L3_n30_k6 | 30 | 6 | 2727.7 | 2727.7 | 2183.8 | 2317.0 | **2055.7** | |

| Method | Avg. energy | Avg. time (s) | Optima found | Avg. gap on proven |
|---|---|---|---|---|
| **ALNS** | **1011.1** | 22.87 | 6/6 | 0.000% |
| Genetic Algorithm | 1021.5 | 20.34 | 6/6 | 0.000% |
| Simulated Annealing | 1084.4 | 23.81 | 6/6 | 0.000% |
| Branch & Bound | 1170.5 | 11.28 | 6/6 | 0.000% |
| Greedy construction | 1232.1 | 0.00 | 0/6 | 13.550% |

Findings, all consistent with theory:

- Branch & Bound **proves optimality on `n = 5…10`** and times out from `n = 12`, placing
  the exact/heuristic crossover at about `n = 10` — one instance further than the previous
  run, and the direct payoff of §5.1's stronger bound: `S6_n10_k3` needed 1.5M nodes and
  never finished in 20 s under the old bound (see §5.1 above); it now proves optimal in
  429K nodes and 13.8 s.
- **All three metaheuristics find every proven optimum**, at 0.000% gap. Greedy finds none,
  averaging 13.6% above.
- **No metaheuristic ever returns below a proven optimum.** The project's main correctness
  check.
- **ALNS has the best average energy** and wins outright on `M3`, `L2` and `L3`. GA ties or
  edges it on `M1`, `M2` and `L1`, so the two are close — close enough that, as the
  significance section below shows, twelve instances cannot distinguish them statistically.
  Both clearly beat SA at scale.
- From `n = 18` up, B&B's value still equals greedy's exactly — it is returning its
  warm-start incumbent, having proved nothing. At `n = 12` and `15` it no longer does: the
  stronger bound's tighter node ordering finds a real incumbent (`M1`: 984.3 vs greedy's
  1035.7; `M2`: 1100.3 vs 1316.1) even where it can't yet prove it optimal.

### What the dual bound actually says

| Instance | Incumbent | Dual bound | Unproved interval |
|---|---|---|---|
| S1–S6 (`n ≤ 10`) | = optimum | = optimum | **0.0%** — proved |
| M1_n12_k4 | 984.3 | 412.6 | 58.1% |
| M2_n15_k4 | 1100.3 | 522.4 | 52.5% |
| M3_n18_k5 | 1564.5 | 567.5 | 63.7% |
| L1_n20_k5 | 1830.5 | 636.1 | 65.3% |
| L2_n25_k6 | 2122.1 | 564.6 | 73.4% |
| L3_n30_k6 | 2727.7 | 743.4 | 72.7% |

Tighter than the column-minimum bound's 66.6–89.2% across the same instances (previous
table, now superseded), but still **wide, and that is the honest finding.** The
assignment-relaxation bound drops subtour elimination entirely, so it still grows slowly
with `n`. These gaps are what a Held–Karp or LP-relaxation bound (still not done, see
"Not done" below) would need to close further.

### §6 Statistical significance

Every table above reports means and bests with no indication of whether a difference is
real or seed noise. `drp/eval/stats.py` adds the standard machinery for comparing several
stochastic solvers over a shared benchmark suite (Demšar 2006): a **Wilcoxon signed-rank
test**, paired by instance, for every pair of methods; a **Friedman test** across all
methods at once with its **Nemenyi** post-hoc critical difference; and **bootstrap
confidence intervals** on each method's average gap. The compared metric is
`{method}_mean_gap_pct` — the gap of the *mean over seeds* to the per-instance reference,
not the best-of-seeds figure the leaderboard uses, because best-of-`n` is optimistic and
high-variance and a poor basis for a paired test. `run_experiments.py` now writes
`results/significance.json` and `report/significance_table.tex` alongside the existing
tables, and `report/report.tex` §"Statistical significance" reads from it.

Run on the committed group (`run_20260909_221514`, 12 instances, `alpha = 0.05`):

| Method | Avg. rank | Mean gap % [95% CI] |
|---|---|---|
| ALNS | 2.08 | 0.81 [0.25, 1.49] |
| Genetic Algorithm | 2.17 | 1.60 [0.34, 3.34] |
| Simulated Annealing | 2.58 | 5.28 [1.42, 9.35] |
| Branch & Bound | 3.33 | 10.36 [3.64, 17.55] |
| Greedy construction | 4.83 | 19.38 [13.80, 24.77] |

Friedman: χ² = 31.74, p = 2.16 × 10⁻⁶, Nemenyi CD (α = 0.05) = 1.761.

The Friedman test rejects equal performance decisively — unsurprising, since it is
dominated by greedy and timed-out B&B trailing badly. Pairwise Wilcoxon confirms exactly
that shape: greedy and B&B are each significantly worse than every metaheuristic (p ≤
0.032), restating the crossover-and-timeout story with a p-value instead of an
equal-looking table entry. **The honest finding is on the other side of it: GA, SA and
ALNS are not pairwise significant from one another** (p ≥ 0.14 throughout, n = 12). ALNS
has the best mean gap and rank, and that is a real trend the data supports — but twelve
paired observations is not enough to call it proven. This is exactly the gap §6 was
scoped to close, and closing it fully needs a larger instance set (more statistical power
among the three metaheuristics), not more testing machinery — the machinery is now in
place and will sharpen automatically whenever the benchmark suite grows.

`tests/test_stats.py` checks the machinery itself: the Nemenyi CD reproduces Demšar's
published table exactly (not just approximately) for `k = 2..10`, a synthetic
consistently-better method is correctly detected as significant while a method compared
against itself is not, and the bootstrap CI brackets a known mean.

**Not built**: performance profiles (Dolan–Moré), ECDF of solution quality, time-to-target
curves, anytime curves, ablation studies and instance-hardness correlation are still open
— §6's significance-testing half is done, its profiling/ablation half is not.

## Verified

Everything below was executed, not assumed.

- **216 tests pass** — 199 fast (~42 s), 17 slow (~50 s).
- Split matches brute-force enumeration on every tested tour.
- B&B matches exhaustive enumeration on all instances small enough to enumerate.
- The lower bound never exceeds the true optimum, at every time limit tested.
- `is_feasible` agrees with an independent checker on 2,400 random solutions.
- Formulation 2 is a valid lower bound on B&B for every `n ≤ 8` instance, and equals it
  when the battery is slack.
- The package reproduces the graded notebook's five proven optima and seven greedy energies
  exactly.
- The CLI runs generate → solve → show → animate → export end to end.
- `report/report.tex` passes a structural check; all `\input` and `\includegraphics`
  targets are produced by the pipeline.
- The Nemenyi critical difference reproduces Demšar (2006)'s published table exactly for
  `k = 2..10` methods, not just approximately.
- Importing `tests/data/toy-n8-k3.vrp` and running B&B proves exactly the optimum the file
  declares, on the rounded `EUC_2D` metric the declaration refers to.
- Every one of the twelve real-geography instances has a feasible construction, and the
  same seed rebuilds the same suite from the untouched source CSV.
- A no-fly circle built in `(lat, lon)` degrees measures the requested radius in
  kilometres in every direction, checked at a latitude where `cos(lat)` is far from 1.
- The visibility distances of all six zone instances are unchanged, to floating-point
  equality, by this branch's `segment_blocked` fix.
- The CLI runs build → solve → export --format qgc, and import → solve, end to end.

### Bugs found and fixed while building this

- **Phantom return-leg in the B&B bound** (described above under §5.1) — a latent flaw
  present since the original bound, exposed once the completion term got tight enough to
  combine with it into an over-tight total. B&B reported "proven optimal" at an energy
  above the true brute-forced optimum on `n = 7` — the single worst failure mode this
  project defines. Caught by `test_bnb_ground_truth.py`.
- **Invalid dual bound** (described above) — would have reported lower bounds above the
  true optimum on timed-out runs.
- **ALNS converging to the wrong place** (described above) — three separate causes, the
  substantive one being a repair operator that scored insertions by distance while the
  objective is load-dependent energy.
- **The dual gap was silently overwritten.** `bnb_gap_pct` was computed twice in
  `instance_rows`: first as the proved interval, then clobbered by the gap-to-reference
  that every method gets. Since B&B usually *is* the reference on small instances, a 66.6%
  unproved interval was being reported as 0.004%. Renamed to `bnb_dual_gap_pct`, with
  `tests/test_metrics.py` written specifically to keep the two apart.
- **A no-fly zone a drone could fly straight through** (described above under §3) — a
  segment entering and leaving a polygon through two *vertices* passed the blocking test.
  Found by a symmetric scenario-builder test, not by the random-geometry ones.
- **A side suite would have silently redefined the report.** `run_experiments.py
  --tables-only` rebuilds the report's tables from the store's *latest* group, so running
  the new geographic suite into `results/runs.db` would have made the report describe it.
  Side suites now keep their own store and leave the report's tables alone.
- **Unescaped `&`** in the generated LaTeX summary table (`Branch & Bound`) — LaTeX reads it
  as a column separator; the table would not have compiled.
- `ndarray.ptp()` was removed in NumPy 2.0 — broke the animation on this machine's NumPy.
- A nonsense zone-overlap check in the zone generator that compared unrelated coordinates.
- `run_experiments.py`'s docstring contained `\input`, raising a `SyntaxWarning`.

### A deliberate behaviour change

The package's B&B explores sibling nodes **cheapest-bound-first**, where the notebook used
customer-index order. It proves the same optima — pinned by the parity test — but visits a
different, generally smaller tree, so **node counts differ from the notebook's**. Energies
and optimality flags are unchanged.

---

## Not done

Listed so nothing looks finished that isn't.

| Roadmap | Item | Note |
|---|---|---|
| §2.1 | Interactive 2D map, drag-and-drop what-if | Needs a web front end |
| §2.3 | 3D altitude, extruded zones, terrain | P5 |
| §2.4 | B&B tree explorer, SA/GA dashboards | The data is in the store; the views are not built |
| §2.5 | SVG/TikZ export, colour-blind-safe theme | Figures are PNG only |
| §3.1–3.3, §3.5 | Scenario builder, real geography, CVRPLIB/Solomon import, QGC export | ✅ Landed — see "P4 — Use it" above. No third-party benchmark files are committed, so the literature comparison is unblocked rather than done |
| §3.4 | Address geocoding, OSM basemaps | Not done: both need network access. The district gazetteer is dataset-derived and labelled as such |
| §4.2 | Wind and asymmetric costs | Would break the 2-opt symmetry assumption — a real change, not a parameter |
| §4.3–4.8 | Climb/hover energy, time windows, multi-trip, deconfliction, uncertainty, multi-objective | P5 |
| §5.1 | Held–Karp / LP / column-generation bounds | Assignment-relaxation bound landed and moved the ceiling from `n ≈ 9` to `n ≈ 10`; a subtour-eliminating bound (Held–Karp 1-tree, LP relaxation) is the remaining, bigger step |
| §5.2 | Tabu, VNS, memetic GA, ACO, island model | Only ALNS added |
| §5.3–5.4 | Learned methods; Numba/Rust performance | Not started |
| §6 | Performance profiles, ECDF, time-to-target/anytime curves, ablations, instance-hardness correlation | Wilcoxon/Friedman+Nemenyi significance testing and bootstrap CIs landed (`drp/eval/stats.py`); the profiling and ablation half of §6 is still not started |
| §7–8 | REST API, Docker, simulator, docs site | Not started |

### Two honest caveats

1. **`report/report.tex` has never been compiled.** No LaTeX toolchain on this machine. It
   passes a structural check and every include target exists, but run
   `pdflatex -output-directory=report report/report.tex` before relying on it.

2. **The *report's* study still uses synthetic instances.** The real geography is now
   wired in — `geo_benchmark_suite()` builds twelve instances from
   `data/source/Last_Mile_Delivery_Coordinates.csv`, and the pilot run above solves them —
   but `default_benchmark_suite()` is still what `run_experiments.py` runs by default and
   what every table in `report/report.tex` describes. Promoting the geographic suite to the
   study of record means re-running the full protocol (5 seeds, 20 s B&B) and re-writing
   the report's numbers, which is a deliberate decision, not a side effect of this branch.

---

## Open questions (roadmap §10)

Still unanswered, and they change what to build next:

1. **Scope** — research artefact (§6 statistics, benchmark import, a paper) or product demo
   (§2 interactive, §7 service)? P3 serves both; after that they diverge sharply.
2. **Language** — stay pure Python, or move hot loops to Rust? Only matters if `n ≥ 200`
   does.
3. **Solvers** — open (CBC/HiGHS/OR-Tools) or an academic Gurobi licence for real
   branch-and-cut?
4. **Geography** — synthetic only, or commit to one real city as the flagship? Pontianak
   is now *available* as a suite; whether it becomes the study of record is still open.
5. **Fidelity** — how physically accurate should the energy model get before extra realism
   stops changing the optimisation conclusions?

My read: §5.1's assignment-relaxation bound is in and moved the ceiling from `n ≈ 9` to
`n ≈ 10` — real, but one step, because the relaxation still has no subtour elimination. §6's
Wilcoxon/Friedman/Nemenyi significance testing is in too, and its headline result is itself
an answer to question 1: **GA, SA and ALNS are not pairwise distinguishable at `n = 12`
instances**, so the confident "ALNS wins" language elsewhere in this document is a trend,
not a proven claim. Closing that needs a larger instance set for statistical power, which
is §3.3's benchmark-library import (CVRPLIB/Solomon) doing double duty — it would answer
question 1 (compete on literature instances) *and* give §6 the sample size it's missing,
probably more efficiently than generating more synthetic instances would. **That importer
now exists**, so the remaining step is no longer engineering: it is downloading a set
(Augerat A/B, Uchoa X, Solomon) and running the protocol over it, at which point §6's
machinery sharpens automatically. A Held–Karp
1-tree or the flow formulation's LP relaxation remains the path to a bigger jump past
`n ≈ 10` whenever the exact side becomes the priority again.
