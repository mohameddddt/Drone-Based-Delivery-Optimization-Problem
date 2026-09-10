# Project progress

Status of `main`, tracked against the project roadmap. Updated 2026-09-10.

## Where this stands

The graded submission is done and unchanged. This document tracks the work *after*
that — turning a 37-cell notebook into software other people can use.

**P1 Foundation is complete, and all six roadmap quick wins are done.** §5.1's stronger
B&B bound and §6's significance testing are now in too. §2.2's playback has been rebuilt
as an interactive GSAP web page, and then rebuilt again around a real pan/zoom map after a
browser-driven design review. **§2.4 is complete**: the B&B tree explorer, the trace
instrumentation it needed — which also unblocked **Solver Vision** in the flight replay,
the one feature the brief asked for that had been deliberately left out — and the
**GA/SA/ALNS convergence dashboard**. **§2.5 is complete too**: vector export, a
colour-blind-safe theme measured rather than asserted, and — three pages overdue — a
headless-browser test harness, with one test for every bug previously found by hand. Every
view is documented in [docs/VISUALISATION.md](docs/VISUALISATION.md). P4 (real geography,
benchmark import, service) and most of P5 are not started.

| Phase | Status |
|---|---|
| **P1 Foundation** | ✅ **Complete** — package, formats, CLI, tests, results store, CI |
| **P2 See it** | ◐ Partial — animated playback ✅ (GIF + pan/zoom GSAP flight-replay page), B&B tree explorer ✅, Solver Vision ✅, convergence dashboard ✅, visualisation guide ✅, SVG/PDF export ✅, colour-blind-safe theme ✅, browser tests ✅; interactive 2D what-if map ✗, 3D ✗ |
| **P3 Mean it** | ◐ Partial — polygonal no-fly ✅, visibility detours ✅, ALNS ✅, dual gap ✅, stronger bound ✅, significance testing ✅; wind ✗, performance profiles/ablations ✗ |
| **P4 Use it** | ✗ Not started |
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
claimed result without re-running a solver. GeoJSON and per-leg CSV export too.

### §1.3 Command-line interface

`drp generate | solve | compare | bench | show | export`, all exercised in CI.

### §1.4 Tests

**165 tests.** The ones the roadmap called for specifically:

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
deliberate: §2.4's B&B tree explorer below reuses the same data-in/choreography-out
pattern, and the SA/GA dashboards will too.

**Solver Vision** (candidate routes considered and rejected) was deliberately absent
through all three of these passes: the brief asks for it and it is the most persuasive
feature on the page, but B&B, GA and SA exposed no intermediate search states, and the
brief's own rule — do not fabricate what the solver does not produce — made faking it the
wrong move. It was blocked on trace instrumentation, not on the front end. §2.4 below built
that instrumentation, and Solver Vision is now in.

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

### §2.4 B&B search-tree explorer

```
drp tree inst.json --time 20 -o tree.html
```

`solve_bnb(..., trace=True)` now records the search: one `BnBNode` per call to `recurse`,
carrying the partial assignment, the node's lower bound, the incumbent standing at that
moment, and how the node ended (`expanded`, `pruned_bound`, `infeasible`, `new_incumbent`,
`dominated`, `timeout`). Each node also lists every branching option it *considered*,
including the ones that never became nodes at all — cut for a forbidden arc, an
over-payload or over-battery route, the symmetry break, or a sterile bound.

That last part is the interesting half. At `n=7` the search **entered** 2,041 nodes but
**considered** 5,107 options; 1,722 of those died on the symmetry break alone and 692 on
the bound, and none of them appear in `nodes_explored`. Most of the pruning is invisible in
the aggregate the solver used to report, and it is exactly what "why did the search never
go down there" means.

The hook is opt-in and off by default — every recording site sits behind one `tr is not
None` test — because `bench` and `compare` run under a time limit and must not regress.
`bound_child` had to change shape (it returns `(bound, survives)` instead of
`Optional[float]`, so the trace can report *what* condemned a cut child), and `survives` is
exactly the old "is not None" test, so the same children are generated and
`nodes_explored` is unchanged. Recording stops at `trace_max_nodes` and sets `truncated`;
the search itself always runs to completion, and a capped run returns exactly what an
uncapped one returns.

**The page.** Same data-in/choreography-out split as §2.2: `drp/viz/treedata.py` emits one
JSON dict, `drp/viz/web/tree_template.html` owns every layout and camera decision. The tree
puts **expansion order across and depth down**, so the horizontal axis is the scrubber's
axis — the playhead sweeps left to right through real search time and a node's subtree sits
immediately to its right. Nodes are filled and their edges coloured by lower bound on a
ramp from the root bound to the final incumbent; radius grows with slack against the
incumbent of the moment; a ring says how the node ended. The bands of solid magenta at
depth are the answer to "why didn't it search there". Clicking a node shows its partial
routes on a small map — closed routes with their return leg, the open route without one,
because `route_energy_open` does not charge one either — plus the options it rejected as
ghost legs coloured by reason.

**One derived series, derived by the solver's own rule.** The rail's "bound closing on
incumbent" chart needs the dual bound at each step, which the trace does not store. It is
computed in the browser as the minimum over every node generated but not yet expanded —
literally the rule `solve_bnb` uses for its reported `dual_bound`, including keeping a
timed-out node on the frontier and adding its stranded siblings at the moment of the
timeout. `tests/test_viz_tree.py` reimplements that rule in Python and asserts the series
lands on `BnBResult.dual_bound` exactly, timeout included. Without that test the curve
would be a plausible picture of a search that never happened.

### §2.4 Solver Vision

```
drp show sol.json --instance inst.json --web flight.html --vision
```

The feature §2.2 deliberately left out, now that there is a trace to build it on. With it
toggled on, selecting a drone draws the options the search considered and rejected at each
point along that drone's route: thin low-opacity ghost legs under the flown route, coloured
by why they were cut, with the node id and bound on hover.

Matching is on **full state** first — the node whose closed routes are the drones already
finished and whose open route is this prefix, i.e. the search building this very solution.
That node is deep on the winning path, working against a strong incumbent, so it actually
rejects things. Falling back to the open-route prefix alone lands on the *first* node to
reach that prefix, which has no incumbent worth the name and explores nearly everything;
those matches are still shown, labelled `(prefix)`.

The honest cases are the point. Replaying B&B's own optimum at `n=7` gives `7/7 route steps
matched a node (7 exact)`. Replaying an **ALNS** solution against a B&B trace that timed out
at `n=14` gives `5/14 (0 exact)` — and the two unmatched drones say so in words: *"The
search never stood at any point on this route, so it has nothing to say about it."* The
solver panel carries the provenance beside the numbers: how many steps matched, how many
exactly, how big the search was, whether it timed out, whether its trace was capped. No
candidate is ever synthesised.

### §2.4 One real finding about the bound

Writing the test the roadmap asked for — *bounds along any root-to-leaf path are
non-decreasing* — found that they are **not**, and the exception is real rather than a
tolerance problem.

`bounds.assignment_completion_bound` returns 0 for an empty completion set. So at the one
branching step that empties the unassigned set, the bound stops charging the
return-to-depot arc that the parent's assignment relaxation had priced, and can fall by up
to that arc's cost. Measured across four instances: **39 of 32,887 transitions, every one
of them into a leaf, none anywhere else.**

This is not a correctness bug — the bound only ever gets *looser* there, so the optimum is
never pruned, which is what `test_bnb_ground_truth.py` verifies end to end. But it is not
monotone, and the test now says so precisely: monotone at every step that leaves work to
do, only leaves may dip, and — the claim that actually matters —
`test_a_leaf_cost_never_undercuts_an_ancestor_bound` asserts that the realised cost of a
complete assignment is never below any bound on the way down to it. Tightening the bound to
charge that arc would change `nodes_explored` and the committed run's numbers, so it was
left alone and written down instead.

### §2.4 Convergence dashboard

```
drp dash inst.json --methods ga,sa,alns --time 5 -o dash.html --reference 10
```

The other half of §2.4. All three metaheuristics already carried
`history: List[float]` — best-so-far, subsampled — which is enough to draw a monotone
staircase and nothing else. `drp/meta/trace.py` adds one shared trace shape for all three,
on the same terms as the B&B trace: opt-in, off by default, one guard per site.

What `history` could not show, and now does:

- **SA** looks like SA because of the *working* solution wandering above the best-so-far,
  and the temperature driving how far it may wander. Both are recorded, reheats marked.
- **ALNS** is adaptive, and the thing worth watching is the operator weights moving as it
  learns. Only the *final* weights were reported; now one record per weight update carries
  the weights, the draw counts and the scores that produced them.
- **GA** is a population, and a best-of-generation line says nothing about whether it
  converged or collapsed. Samples carry population mean and spread — over the *feasible*
  members only, since Split returns `inf` for a tour no fleet can serve and one `inf` would
  swallow the mean.

**Bounded by decimation, not truncation.** A 5 s SA run does ~8,700 iterations. The tracer
keeps every stride-th step and, when the buffer fills, drops every second sample and
doubles the stride — so the buffer is a *uniform* sample of the whole run at all times, at
O(1) amortised cost. Truncating to the first N points instead would show the opening of the
search and nothing after it, which for a convergence curve is the one useless shape.
Improvements and reheats are recorded separately and in full, so no marker is ever dropped.

**Where the invariance claim actually falls.** For a **fixed** iteration/generation budget
the trace changes nothing — same solution, energy, history and counters, asserted for all
three across three seeds. Under a **wall-clock** limit it is not true and is not claimed:
recording costs time, so fewer iterations fit, exactly as any other overhead would. That is
why `bench` and `compare` leave it off, and why every invariance test pins a fixed budget
and a generous clock.

**The page** puts all three methods on one pair of axes, which needs two things handled
rather than assumed. Wall-clock seconds is the default x-axis, because one GA generation
evaluates `pop_size` tours and one SA iteration evaluates one; the step axis is still
offered and is labelled *not comparable across methods* when selected. And the vertical
range fits the best-so-far curves rather than everything — an SA working solution wanders
far above every answer, and a range containing it squashed all three bests into a band a
few pixels tall, which was the one thing the chart existed to show.

`--reference SECONDS` runs B&B too and draws a floor. If B&B proves optimality that floor
is the optimum; if it does not, the floor is its **dual bound** and is labelled as such,
because an unproven incumbent is not a floor and drawing it as one would misstate what is
known.

### §2.4 What the dashboard found about SA

The first thing the view was pointed at, it answered — which is the point of building it.

On the n=14 worked example SA reports 1214.7 against GA's 1095.4 and ALNS's 1119.5, and its
panel reads **`Improvements on the start: 0`**. It never beat the greedy warm start it was
handed, in 8,700 iterations.

That is not a one-instance accident. Measured at a 3 s budget, warm-started from
`best_construction`, improvement counts summed over seeds 1–3:

| Instance | Warm start | SA best | SA improvements | ALNS | GA |
|---|---|---|---|---|---|
| n=10, K=3 | 954.0 | **851.2** | 16 | 851.2 | 851.2 |
| n=14, K=4 | 1155.5 | 1085.8 | 2 | 1029.8 | 1029.8 |
| n=20, K=5 | 2200.7 | 1843.7 | 1 | 1700.4 | 1680.6 |
| n=25, K=6 | 2299.3 | 2085.7 | 0 | 1959.8 | 1919.2 |

At n=10 SA matches ALNS and GA exactly. By n=25 it makes no improvement at all, and the gap
to the other two is ~7%.

The temperature panel shows the likely mechanism. `solve_sa` calibrates `T0` once from 60
random-neighbour deltas so early acceptance is ~0.8, then cools at `gamma=0.9995`. Over
8,700 iterations that would take `T` to about 1.3% of `T0` — cold enough to consolidate.
It does not get there: `reheat_after=4000` fires twice in a 5 s run, and each reheat resets
`T` to `T0 * 0.5` *and* throws the working solution back to the incumbent. The trace ends
at `T ≈ 235` against energies around 1,200, i.e. still accepting almost anything. SA spends
the whole budget in a near-random walk and never gets to exploit.

**Not changed here, deliberately.** Retuning `gamma`, `reheat_after` or the calibration
would move `SAResult` on every instance, and the committed run's numbers and
`test_notebook_parity.py` are pinned to the current behaviour. It is written down as a
measured finding with a mechanism, and belongs with §6's ablations rather than in a
visualisation change.

### §2.4 What the browser found this time

Eight things, none visible in the source and all obvious on screen — the same lesson as
§2.2. **In the tree explorer:**

1. **The tree rendered as a black mass with no nodes in it.** Every node's incoming edge
   lived inside that node's own `<g>`, so each later edge painted over every earlier
   circle. Edges and circles are separate layers now, and edges are coloured by the bound
   of the node they feed, which turns the mass of strokes from noise into the bound field
   itself.
2. **Three temporal-dead-zone crashes.** `readout` and `visionStroke` are read during
   camera setup and `playing` during the first `setT`, all before their `let`/`const`
   declarations execute. Note that `typeof x !== "undefined"` does *not* guard this — on a
   `let`/`const` in its TDZ, `typeof` throws too.
3. **"Next improvement" was dead on arrival**, because the page opens with the playhead at
   the end of the search where there is no next improvement. It wraps now, and the page
   opens on the node that produced the answer rather than the root, which had the inspector
   contradicting the playhead.
4. **The rail was height-bound to the tree**, hiding the mini map behind an inner
   scrollbar. The tree panel stretches to the row instead — safe here, unlike §2.2's bug,
   because the rail's height does not depend on the tree panel's width.
5. **The colour encoding collapsed on the run where it mattered most.** A search that times
   out without ever finding a feasible solution has no incumbent, so the ramp
   root-bound-to-incumbent had zero span and every node came out the same colour — in
   exactly the run where the bound is the only thing there is to look at. The ramp falls
   back to the range of bounds actually recorded, and the legend prints both ends as
   numbers and says which it is showing.

**In the convergence dashboard**, all three about the vertical axis, which turns out to be
where a multi-method chart goes wrong:

6. **All three answers squashed into an illegible band.** The y-range contained SA's
   working solution, which wanders far above every best-so-far curve — so the curves the
   chart exists to compare occupied a few pixels at the bottom. The range now fits the
   best-so-far series, working solutions are clipped, and the page names the curves it
   clipped rather than letting the legend promise a line the reader cannot find.
7. **The reference floor spent half the plot proving a gap.** On a hard instance B&B's
   dual bound sits far below every method, and including it in the range left ~55% of the
   chart empty. In `fit best` it is now an edge marker plus a per-method gap percentage —
   a number is the better way to read that gap; `fit all` still gives it the axis.
8. **Every readout said `–` at the natural starting position.** The x-domain began at 0
   but the first sample lands a few milliseconds in, so pressing `Home` landed in a sliver
   where no method had produced a sample. The domain starts at the first real sample now.

And one found by writing the guide rather than the code: **none of the pages degrades when
its CDN is unreachable — they do not render at all.** Every element is built by their
script and that script needs GSAP, so an offline user got a shell of empty panels and no
explanation. All three now detect the missing library and say what happened.

### §2.4 Coverage

`tests/test_bnb_trace.py` (53 tests) treats the trace as a claim about the search rather
than a data structure to smoke-test: one record per node entered, every parent id present,
candidate→child links real in both directions, child states composing from parent state and
candidate, pruned nodes genuinely dominated by the incumbent they were compared against,
and — the one that protects everything else — identical solution, energy, node count and
dual bound with tracing on and off.

`tests/test_viz_tree.py` (17 tests) covers both payloads: the explorer's geometry covers
every leg it can be asked to draw and detours where the distance matrix detours, the
derived dual-bound series lands on the solver's own, and Solver Vision never reports an
option that was taken.

`tests/test_meta_trace.py` (33 tests) does the same for the metaheuristic traces —
fixed-budget invariance for all three, ordering and end-state, every improvement recorded
as an event, SA's temperature falling except where it reheats, ALNS's final segment
matching the weights the solver reports, and decimation staying uniform and never dropping
an event. `tests/test_viz_dash.py` (12 tests) covers the dashboard payload: the shared axis
limits contain every series, the three numbers that must agree do, and no method may report
an energy below a proven optimum.

**280 tests** at this point, and still no browser test harness — none of the JavaScript
above was covered by CI, and every bug listed was found by driving the pages in Playwright
by hand. §2.5 below closes that: `tests/browser/` now drives all three pages in headless
Chromium, with one test named after each of those bugs.

### §2.5 Vector export

`drp show -o routes.svg` works, and so do `.pdf`, `.eps` and `.ps`. There is no
`--format` flag and there does not need to be one: matplotlib reads the suffix, and the
single save point only had to stop forcing a raster dpi on a vector target. Two details
that are not obvious: matplotlib stamps a creation date into SVG and PDF, which makes
every regeneration a diff, so both are stripped; and `dpi` is now applied to raster
targets only.

`generate_figures.py` writes every figure **twice**, as PDF and PNG. PDF rather than SVG
because `report/report.tex` is built with pdflatex, which embeds a PDF directly, while an
SVG needs `--shell-escape` and an Inkscape on the build machine — a dependency the report
does not otherwise have. The `\includegraphics` calls lost their `.png` suffix, so LaTeX
takes the PDF and falls back to the PNG if the vector file is missing. PNG stays because
plenty of things that are not LaTeX read these files. SVG is one flag away (`--formats
svg`) and is not written by default because nothing in the repository consumes it.

**TikZ: considered, rejected, written down rather than half-added.** Over PDF it buys
exactly one thing — figure text set in the document's own font, at the document's own
size, by the same typesetter. It costs a matplotlib-to-TikZ dependency, a build that can
now fail inside LaTeX rather than inside Python, and tens of thousands of generated lines
of `.tex` per data-heavy figure; `fig_comparison` alone draws 60 bars. If the report ever
does need figure text to match exactly, the cheap half of that is matplotlib's own `pgf`
backend, which needs no new Python dependency.

### §2.5 What vector output exposed

The roadmap's warning was right, and the specific number is worse than expected. A figure
drawn 7.5 inches wide and placed at `0.65\textwidth` — 4.09 inches in this report's A4,
2.5 cm-margin geometry — is shrunk to **0.55** of its size by LaTeX. That takes 11 pt text
to 6 pt and an 8 pt customer label to **4.4 pt**. Across the seven figures the range was
4.3–5.8 pt for annotations and 5.4–7.2 pt for tick labels: below any readable floor.

At `dpi=150` this was invisible, and that is the interesting part. A 4 pt label rasterises
to a grey smudge that reads as "fine print", and nobody looks closer. In vector it is
crisp, and unmistakably too small. The raster output was not hiding a rendering bug; it
was hiding a *typographic* decision nobody had made.

Fixed by having each figure declare the fraction of `\textwidth` it is printed at
(`generate_figures.py`'s `PLACED_AT`, which has to stay in step with the
`\includegraphics[width=…]` calls) and sizing type and strokes so they land at 9 pt
headings, 8 pt ticks and 7 pt annotations *on the page*. Line widths and marker sizes scale
with them — a 1.8 pt route stroke shrunk to 1.0 pt is a hairline, and a hairline is the
first thing to disappear in print. Annotation *offsets* scale too, which was needed as
soon as the type grew: bigger labels sat on top of their own markers.

`drp show` passes no `placed_at`, because a figure someone asked for by name is not going
into that report.

### §2.5 A colour-blind-safe theme, measured

`drp/viz/theme.py` holds both palettes; `--theme`, `DRP_VIZ_THEME` and a `theme=` argument
on every drawing entry point select one. `safe` is the default; `chart` is the original,
every hex unchanged. Be precise about what that promises: it restores the *palette*, not a
pre-§2.5 figure, because the type resizing below applies to both themes. The pages no
longer carry a palette of their own: the theme travels in the JSON payload and is written into the CSS
custom properties at startup, so **one Python constant now colours all five views**.

"Safe" is a claim until something measures it, so `drp/viz/cvd.py` implements the standard
simulation — Viénot, Brettel & Mollon (1999) for protanopia and deuteranopia, Brettel,
Viénot & Mollon (1997) for tritanopia — and CIE76 dE\*ab for the distance.

The old palette, simulated. Its worst pair:

| Vision | Closest pair, dE | Which |
|---|---|---|
| normal | 26.2 | blue / purple |
| protanopia | 9.4 | blue / purple |
| **deuteranopia** | **7.8** | **red / green** |
| tritanopia | 16.4 | green / purple |

dE 7.8 is "the same colour with a bad print". `safe` scores **29.5** at its worst pair
across all three deficiencies, every colour clears 3:1 contrast against the page
background, and the route colours are held clear of the *semantic* ones so no hex means
two things. `results/fig_theme.pdf` draws both palettes as each kind of vision receives
them; the dashboard's method colours (purple / red / blue, whose red and blue collapse
under protanopia) and the replay's delivered-green / breach-red pair are fixed by the same
switch.

**Two things worth recording about how this was arrived at.** First, hand-picking a
palette that *looks* safe does not work: a designed set of navy / vermillion / teal /
purple / amber / sky measured **4.2** under protanopia — worse than the palette it was
meant to replace. It was replaced by a maximin search over a contrast-filtered grid, and
the result is machine-derived rather than hand-chosen, which is the honest description.
Second, published "colour-blind safe" sets are not automatically safe *here*: measured on
this cream background, Paul Tol's *bright* scheme collapses to dE 1.4 under tritanopia and
ColorBrewer *Dark2* to 4.5 under deuteranopia. Half of Okabe–Ito fails the contrast floor
outright, because it was designed for white.

### §2.5 One real finding about the bound ramp

The roadmap guessed the tree explorer's teal → amber → magenta ramp was "already close to
safe" and asked for it to be checked rather than assumed. Checked, it is **not safe, and
the failure is worse than a confusable pair**. A sequential ramp has to be monotone in
perceived distance from its own start, or a high value looks like a low one. Sampled at
nine points, dE from the first stop:

| Vision | first → last |
|---|---|
| normal | 0 → 12 → 27 → 43 → **60** → 56 → 57 → 65 → 76 |
| protanopia | 0 → 11 → 23 → 35 → **46** → 31 → 17 → 14 → 28 |
| deuteranopia | 0 → 13 → 28 → 43 → **58** → 45 → 30 → 15 → **9** |
| tritanopia | 0 → 8 → 19 → 32 → **50** → 46 → 51 → 56 → 59 |

Under deuteranopia the ramp's far end lands dE 9 from its near end while its middle is 58
away: it folds back, and the highest bounds are drawn in the same colour as the lowest —
in the one view where the bound is the entire point. It is not monotone for **any** of the
four, normal vision included; the deficiencies only make an existing flaw severe. `safe`'s
ramp is navy → violet → amber, monotone under all four, spanning at least dE 63.

### §2.5 Colour is never the only channel

No palette helps a monochromat, and none survives a fax, so every theme carries a dash
pattern, a marker shape and a bar hatch indexed on the same number as the colour. Routes
get a dash in the static plot, the GIF and the replay — and the manifest row's spine
repeats it. Methods get a dash and a marker everywhere, and the dashboard's legend rules
are drawn as tiny SVGs so they carry the *exact* pattern the curve does. Tree node
statuses get a ring dash, which matters most there because the fill under the ring is
itself a ramp colour. Bars get a hatch. Delivered is a filled disc with a tick, pending an
empty outline, a breach a dashed ring with the numbers beside it.

The second channel is identical in both themes, so switching theme changes only the
colour and a figure's *shapes* stay comparable.

**What it does not fix, stated plainly.** Six route colours, five semantic ones and a
sequential ramp cannot all be mutually far apart at 3:1 contrast on a cream page. The
tightest route-versus-semantic pair in `safe` is dE 11.2 — a dark red route against the
crimson a breach flashes in. That is a limit, not an oversight, and it is exactly why the
shapes above exist.

**One behaviour change.** `drp/viz/static.py` and `drp/viz/dashdata.py` held two
*different* method-colour maps: static's `ga` was blue, dashdata's was purple. The theme
unifies them, so `--theme chart` draws the dashboard in static's mapping rather than
dashdata's. No committed figure moves — those all come from `static.py`.

### §2.5 A browser test harness, three pages overdue

`tests/browser/` — **67 tests** across the three pages, in headless Chromium. What they
assert beyond "it rendered": no page error and no console error, the GSAP guard did not
fire, panels are populated rather than empty shells, the numbers on the page are the
numbers in the payload that produced them, play advances and scrubbing seeks and selection
fills the inspector and the axis and fit toggles change the chart, and nothing overflows
sideways at 430 px.

And one test per bug found by hand, named after it:

| Test | The bug |
|---|---|
| `test_no_uncaught_errors_anywhere_on_load` | The three temporal-dead-zone crashes. They threw *and* left a partly built page, so an element-counting smoke test would have passed |
| `test_next_improvement_wraps_instead_of_doing_nothing` | "Next improvement" dead on arrival at the end of the search |
| `test_fit_best_does_not_squash_the_curves_into_a_band` | Measured: `fit best` gives the best-so-far curves 79% of the plot height, `fit all` 2%. Anything under a quarter is the bug back |
| `test_home_does_not_leave_every_readout_empty` | Every readout `–` at `Home` |
| `test_edges_and_nodes_are_in_separate_layers` | The tree as a black mass with no nodes in it |
| `test_seeking_backwards_un_fires_events` | The documented promise nothing enforced |
| `test_the_rail_is_height_bound_to_the_map_on_desktop` | The map painting over the manifest |
| `test_the_mini_map_is_not_hidden_behind_a_scrollbar` | The tree explorer's rail bound the wrong way |

**Three harness decisions.** GSAP is served from a local cache rather than the CDN, so a
network hiccup cannot look like a test failure; fonts are fulfilled *empty* rather than
aborted, because an aborted request logs a console error and the console-error list is
supposed to be empty. Pages load with `prefers-reduced-motion: reduce`, so the DOM reaches
its final state on the first frame and no assertion races an intro tween — with one test
loading with motion on and asserting it settles in the same place, which is the only thing
that has ever actually checked that claim. And the tree fixture runs `--no-warm-start` on
purpose: with a warm start the search often has no improvements, and the button whose
deadness is being tested would have nothing to do.

**Writing them found one more bug — in the test tooling, not the product.** The first
tritanopia implementation applied Brettel's separation plane in LMS, where its normal is
defined in linear RGB. Mid-grey came out `#3A4500`. A neutral grey must be fixed under
every simulation, `test_simulation_leaves_neutral_greys_alone` says so, and it caught it.
Every number in this section is from the corrected transform.

**In CI**, they run in their own job on **every push and every pull request**, not only on
`main`: the whole reason the job exists is that JavaScript regressions are invisible in
review, and deferring it to `main` means a pull request can break a page and merge green.
Honest cost — ~40 s to install, ~25 s for Chromium on a cache hit (90 s cold, once per
Playwright version), ~60–75 s for the tests: **about 2 minutes warm, 3 cold**, in parallel
with the existing jobs. They are marked `slow` as well as `browser` so `-m "not slow"`,
the fast subset, is unchanged.

### §2.5 Coverage

`tests/test_viz_theme.py` (33 tests) treats the theme as a claim rather than a constant.
The simulation is checked first, against behaviour that does not come from this repository
— neutral greys fixed, red and green collapsing onto one yellow under protanopia and
deuteranopia and *not* under tritanopia, blue untouched by protanopia and destroyed by
tritanopia. Then the claims: the safe palette's worst pair, its contrast on the page, that
no colour carries two meanings, that the ramp is monotone under all four, that the second
channel exists and is unique per series, and that `chart`'s hexes are still the original
ones. Vector export is covered too: the extension chooses the format for `.png`, `.svg`,
`.pdf` and `.eps`; the two themes produce different files; `placed_at` changes the type
and not the figure's dimensions; and regenerating a figure gives the same bytes.

`tests/browser/` (67 tests) is described above.

**390 tests**, and for the first time the JavaScript is among them.

---

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

- **165 tests pass** — 148 fast (~35 s), 17 slow (~45 s).
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
| §2.4 | — | **Done.** B&B tree explorer, Solver Vision and the GA/SA/ALNS convergence dashboard are all in |
| §2.5 | TikZ export | Considered and rejected, with the reasoning written down in `generate_figures.py`. `pgf` is the cheaper thing to try first if the report ever needs it. SVG/PDF export and the colour-blind-safe theme are done |
| §3.x | Scenario builder, geocoding, OSM basemaps, CVRPLIB/Solomon import, QGC export | Nothing started. Haversine distances exist (`geodesic=True`) but no importer uses them |
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

2. **The study still uses synthetic instances, not the supplied dataset.**
   `data/source/Last_Mile_Delivery_Coordinates.csv` is restored and
   `notebooks/data_instance_builder.ipynb` runs against it, but
   `default_benchmark_suite()` samples coordinates uniformly at random. Wiring the real
   geography into the benchmark is roadmap §3.2 and is not done.

---

## Open questions (roadmap §10)

Still unanswered, and they change what to build next:

1. **Scope** — research artefact (§6 statistics, benchmark import, a paper) or product demo
   (§2 interactive, §7 service)? P3 serves both; after that they diverge sharply.
2. **Language** — stay pure Python, or move hot loops to Rust? Only matters if `n ≥ 200`
   does.
3. **Solvers** — open (CBC/HiGHS/OR-Tools) or an academic Gurobi licence for real
   branch-and-cut?
4. **Geography** — synthetic only, or commit to one real city as the flagship?
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
probably more efficiently than generating more synthetic instances would. A Held–Karp
1-tree or the flow formulation's LP relaxation remains the path to a bigger jump past
`n ≈ 10` whenever the exact side becomes the priority again.
