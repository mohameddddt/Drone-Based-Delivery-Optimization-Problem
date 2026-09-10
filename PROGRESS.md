# Project progress

Status of `main`, tracked against the project roadmap. Updated 2026-09-10.

## Where this stands

The graded submission is done and unchanged. This document tracks the work *after*
that — turning a 37-cell notebook into software other people can use.

**P1 Foundation is complete, and all six roadmap quick wins are done.** §5.1's stronger
B&B bound and §6's significance testing are now in too. §2.2's playback has been rebuilt
as an interactive GSAP web page, and then rebuilt again around a real pan/zoom map after a
browser-driven design review. **§2.4's B&B tree explorer is in**, along with the trace
instrumentation it needed — which also unblocked **Solver Vision** in the flight replay,
the one feature the brief asked for that had been deliberately left out. Every view is now
documented in [docs/VISUALISATION.md](docs/VISUALISATION.md). P2's remaining pieces (SA/GA
dashboards, SVG export), P4 (real geography, benchmark import, service) and most of P5 are
not started.

| Phase | Status |
|---|---|
| **P1 Foundation** | ✅ **Complete** — package, formats, CLI, tests, results store, CI |
| **P2 See it** | ◐ Partial — animated playback ✅ (GIF + pan/zoom GSAP flight-replay page), B&B tree explorer ✅, Solver Vision ✅, visualisation guide ✅; SA/GA dashboards, SVG export ✗ |
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

### §2.4 What the browser found this time

Five bugs, none of which were visible in the source and all of which were obvious on
screen — the same lesson as §2.2:

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

And one found by writing the guide rather than the code: **neither page degrades when its
CDN is unreachable — it does not render at all.** Every element on both pages is built by
their script and that script needs GSAP, so an offline user got a shell of empty panels and
no explanation. Both pages now detect the missing library and say what happened.

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

**235 tests.** Still no browser test harness, so none of the JavaScript above is covered by
CI; the five bugs listed were found by driving the pages in Playwright by hand. That
remains the obvious next hardening step, and it is now overdue for two pages rather than
one.

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
| §2.4 | SA/GA convergence dashboards | The B&B tree explorer is built; GA/SA/ALNS already carry a `history` trace and ALNS reports final operator weights, so these need almost no new instrumentation — only per-segment weights to animate ALNS adaptation |
| §2.5 | SVG/TikZ export, colour-blind-safe theme | Figures are PNG only |
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
