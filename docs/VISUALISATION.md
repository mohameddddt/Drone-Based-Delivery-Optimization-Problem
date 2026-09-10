# Visualising a run

Five views, all reachable from the command line:

| View | Command | Output |
|---|---|---|
| Static route plot | `drp show … -o routes.png` | PNG |
| Animated playback | `drp show … --animate flight.gif` | GIF (or MP4) |
| Interactive flight replay | `drp show … --web flight.html` | one self-contained HTML file |
| B&B search-tree explorer | `drp tree … -o tree.html` | one self-contained HTML file |
| Convergence dashboard | `drp dash … -o dash.html` | one self-contained HTML file |

This document is meant to be driven start to finish from an empty directory.
Every command below was executed before it was written down; the timings and
file sizes are from those runs, on an ordinary laptop.

For *why* the views look the way they do, see `PROGRESS.md` §2.2 and §2.4.

---

## Before you start

From the repository root, once:

```bash
pip install -e .
drp --help
```

That puts the `drp` command on your path. Everything below can then be run from
any directory.

**The three HTML pages need a network connection when you open them.** They are
self-contained in the sense that matters — no server, no build step, no sibling
files, just double-click the file, and the instance, the solution and the traces
are all inside — but each one pulls GSAP from cdnjs.cloudflare.com and its two
typefaces from Google Fonts at load time.

Be clear about what happens if that fails: **the page does not degrade
gracefully, it does not render at all.** Every element on all three pages is
built by their script, and that script needs GSAP. Rather than leave you with a
shell of empty panels and no explanation, each page detects the missing library
and says so:

> **This page could not load GSAP** — The file is self-contained apart from one
> thing: it fetches the GSAP animation library from `cdnjs.cloudflare.com` […]
> That request did not succeed — most likely this machine is offline, or
> something is blocking the CDN.

---

## The worked example

Copy-paste, in an empty directory:

```bash
drp generate --n 14 --drones 4 --zones 2 --seed 7 -o inst.json
drp solve inst.json --method alns --time 5 -o sol.json
drp show sol.json --instance inst.json -o routes.png --web flight.html
```

What that prints, and what it leaves behind:

```
wrote inst.json  (n=14, K=4, payload=16.7, battery=862.1, zones=2, nofly_edges=0)
instance : instance  (n=14, K=4)
method   : alns
energy   : 1119.50
feasible : True (feasible)
time     : 5.00s
  drone 1: [14, 10, 9, 4]
  drone 2: [6, 13, 3, 7]
  drone 3: [12, 8]
  drone 4: [5, 11, 2, 1]
wrote sol.json
wrote routes.png
wrote flight.html
```

| File | Size | What it is |
|---|---|---|
| `inst.json` | 3.8 KB | the instance, `drp-instance/v1` |
| `sol.json` | 5.6 KB | the solution and its feasibility certificate, `drp-solution/v1` |
| `routes.png` | 112 KB | the static plot |
| `flight.html` | 107 KB | the interactive replay |

**`flight.html` opens directly in a browser. There is no server to start.** Open
it from your file manager, or:

```bash
# macOS
open flight.html
# Linux
xdg-open flight.html
# Windows
start flight.html
```

The whole thing takes about 10 seconds, five of which are the solver's own time
budget.

To add the search-tree explorer for the same instance:

```bash
drp tree inst.json --time 20 -o tree.html
```

---

## 1. Static route plot

```bash
drp show sol.json --instance inst.json -o routes.png
```

**For:** a figure for a report or a slide. This is the one that goes in the
paper.

**Needs:** a solution JSON and its instance JSON.

**Cost:** about 1 second, ~110 KB at n=14. Scales with the number of routes, not
much else.

One matplotlib figure: depot, customers, one colour per drone, routes drawn
along the path actually flown (bent around any polygonal no-fly zone, not
straight through it), and the total energy in the title. `-o` is required in the
sense that it always writes something — it defaults to `routes.png` — so `show`
never runs without producing the static plot, even when you only wanted `--web`.

---

## 2. Animated playback (GIF / MP4)

```bash
drp show sol.json --instance inst.json -o routes.png --animate flight.gif
drp show sol.json --instance inst.json -o routes.png --animate flight.mp4
```

**For:** dropping into a slide deck or a README, where an HTML page cannot go.
Every drone flies on one shared clock, batteries drain, trails build, and two
aircraft closer than the separation minimum flash red.

**Needs:** the same two files. The output format comes from the **extension**:
`.gif` is rendered by Pillow, which ships with matplotlib; **`.mp4` needs
`ffmpeg` on your path** and will fail without it.

**Cost, at n=14 with the defaults (160 frames, 20 fps):**

| Output | Time | Size |
|---|---|---|
| `flight.gif` | ~31 s | 2.3 MB |
| `flight.mp4` | ~19 s | 126 KB |

The GIF is by far the more expensive and the more bloated of the two; use MP4
when you can. Time and size both scale roughly linearly in `--frames`.

Tuning:

```bash
drp show sol.json --instance inst.json -o routes.png --animate flight.gif \
  --frames 90 --fps 15 --separation 5 --title "L2 fleet playback"
```

---

## 3. Interactive flight replay

```bash
drp show sol.json --instance inst.json -o routes.png --web flight.html
```

**For:** actually understanding a solution — where each drone went, when, why
that route and not another, and where the fleet came close to itself.

**Needs:** the same two files.

**Cost:** ~2 s, ~107 KB at n=14. Both are nearly flat in instance size; the page
is mostly template.

Everything is in the one file: the payload from `drp/viz/webdata.py` is inlined
into `drp/viz/web/playback_template.html`. Nothing is fetched except GSAP and
the fonts.

### Controls

None of these are discoverable from the command line, so:

**The map**

| Do this | Get this |
|---|---|
| Drag | Pan, with inertia on release |
| Wheel / trackpad scroll | Zoom toward the cursor |
| Pinch | Zoom, on touch |
| `+` / `−` / `RST` buttons | Zoom in, zoom out, reset the view |
| Arrow keys | Pan (with the map focused) |
| `0` | Reset the view |
| Double-click | Reset the view |

**Playback**

| Do this | Get this |
|---|---|
| `Space` | Play / pause |
| The play button | Play / pause |
| `0.5× 1× 2× 4×` | Playback speed |
| Drag anywhere on the timeline | Scrub. Seeking backwards un-fires events, so the replay stays a replay |
| Click an event diamond in the timeline | Jump to that moment |
| `Fleet sweep` | Pull back, brighten every route, redraw them from the hub outward, settle home |

**Focus**

| Do this | Get this |
|---|---|
| Click a drone on the map, or its manifest row | Dim the rest, frame its route, redraw its trail, open "why this route" |
| Click the same row again | Deselect |
| Click the map background | Deselect |

The page honours `prefers-reduced-motion`: with it set, the choreography is
skipped and every transition resolves instantly. Nothing becomes unreachable.

### Reading the separation number

This is the most misreadable number on the page, so, plainly:

- **It defaults to 3% of the field span** — the larger of the x and y extents of
  the instance's coordinates. Override it with `--separation`.
- **It is a visualisation-derived metric, not a solver constraint.** Nothing in
  the model enforces separation. No solver has ever seen this number. A
  "predicted breach" is not an infeasibility; it is a conflict that a
  deconfliction model *would* have to resolve, and building that model is
  roadmap §4.5, which is not done.
- **Breaches are only counted outside the terminal-area radius**, which the
  solver panel displays. Every drone departs the same point at the same instant,
  so without that exclusion the whole fleet is inside the separation minimum
  before it has flown anywhere, and a perfectly good solution opens the page
  reporting conflicts it does not have. The radius is shown rather than quietly
  applied, because it is an assumption the model itself does not make.

The same default and the same 3% rule apply to `--animate`, so the GIF and the
page flag the same conflicts.

### Solver Vision

```bash
drp show sol.json --instance inst.json -o routes.png --web flight.html \
  --vision --vision-time 10
```

Adds a `Solver vision` button to the transport bar. With it on, selecting a
drone draws the options a Branch & Bound search *considered and rejected* at
each point along that drone's route — thin low-opacity ghost legs under the
flown route, coloured by why they were cut, with the node id and the bound on
hover.

This runs a **second, separate** B&B search over the same instance
(`--vision-time` seconds, `--max-nodes` trace records). It is not the search that
produced `sol.json` — in the example above `sol.json` came from ALNS. That
matters, and the page does not hide it. The solver panel reports how many route
steps matched a node in the trace, how many matched on full state rather than
just the open-route prefix, how large the search was and whether it timed out:

```
  solver vision: 5/14 route steps matched a node (0 exact) in a 178702-node B&B search
```

Where the search never stood at a given point in a route, **nothing is drawn**
and the panel says so. No candidate is ever synthesised.

Vision is at its most useful on an instance B&B can actually finish (n ≲ 10),
replaying B&B's own solution — note that this is a *different, smaller* instance
than the worked example above, which B&B cannot finish:

```bash
drp generate --n 7 --drones 3 --zones 2 --seed 7 -o small.json
drp tree small.json --time 20 -o tree7.html --solution bnbsol.json
drp show bnbsol.json --instance small.json -o routes7.png --web flight7.html \
  --vision --vision-time 20
```

That prints `solver vision: 7/7 route steps matched a node (7 exact) in a
2041-node B&B search`: every step of every route lands on the node where the
search stood exactly there, building exactly this solution.

---

## 4. B&B search-tree explorer

```bash
drp tree inst.json --time 20 -o tree.html
```

**For:** seeing why the search never went down most of the tree. The tree is
laid out with **expansion order across and depth down**, so the horizontal axis
is the same axis the scrubber runs on: the playhead sweeps left to right through
real search time, and a node's whole subtree sits immediately to its right.

**Needs:** an **instance** JSON — not a solution. `tree` runs the search itself,
with tracing on.

**Cost** (`--time 20`, default `--max-nodes 4000`, 2 zones, K=4):

| Instance | Wall clock | `tree.html` | What the search did |
|---|---|---|---|
| n=7, K=3 | ~1.4 s | 1.0 MB | proven optimal, 2,041 nodes — the **whole** tree fits under the cap |
| n=8 | ~1.8 s | 2.0 MB | proven optimal, 13,373 nodes |
| n=10 | ~8.5 s | 2.4 MB | proven optimal, 183,341 nodes |
| n=14 | ~21.5 s | 3.0 MB | timed out at the 20 s budget, ~400,000 nodes, gap 56.9% |

The runs that finish are reproducible node-for-node. The n=14 row is not: it is
cut off by the clock, so how far it gets depends on the machine and the load.

Wall clock is dominated by the search, so it tracks `--time`. File size is
dominated by the trace: roughly **500 bytes per recorded node**, so
`--max-nodes` is the knob that controls it.

**Use n ≤ 8 if you want a complete tree.** Above that the trace is a prefix — the
first `--max-nodes` nodes in depth-first order — and the page says so in red at
the bottom:

> **Trace capped at 4,000 nodes** — the search explored 358,927; this is its
> first 4,000 in depth-first order. The search itself was not truncated.

That last sentence is the important one: **the cap bounds the recording, not the
search.** A capped run returns exactly the solution, energy, node count and dual
bound an untraced run returns. Tracing is opt-in and off by default everywhere
else, so `bench` and `compare` are unaffected.

### What is on the page

- **The tree.** Each node is filled and its edge coloured by its lower bound, on
  a ramp from the root bound (teal) to the final incumbent (magenta); node
  radius grows with how much slack it had against the incumbent standing at the
  time. The legend prints the ramp's two ends as numbers. On a run that never
  found a feasible solution there is no incumbent to span to, so the ramp spans
  the deepest bound recorded instead, and the legend says so. A ring marks how the node ended: magenta for pruned by bound, green for
  a new incumbent, amber for the node the clock stopped at, grey for an
  infeasible or dominated leaf. The bands of solid magenta at depth are the
  answer to "why didn't it search there".
- **The incumbent path**, drawn in accent teal from the root to the leaf that
  produced the returned solution.
- **The scrubber**, over node-expansion order. Green ticks mark improvements;
  `◀ improve` / `improve ▶` jump between them, wrapping.
- **Bound closing on incumbent.** Two series over expansion order: the incumbent
  as the search saw it, and the dual bound — the minimum over every node
  generated but not yet expanded, which is exactly the rule `solve_bnb` uses for
  the bound it reports. `tests/test_viz_tree.py` reimplements that rule in
  Python and asserts the series lands on `BnBResult.dual_bound` exactly.
- **The node inspector.** Click any node: its status, bound, the incumbent at
  that moment, the slack between them, its closed routes, its open route, and
  what is still unassigned.
- **A small map** of that node's partial assignment — closed routes drawn with
  their return-to-depot leg, the open route drawn without one (because
  `route_energy_open` does not charge one either) and its tip ringed, with the
  rejected options as dashed ghost legs.
- **Options considered.** Every branching option that node looked at, and what
  became of it: `explored`, or cut on `bound`, `payload`, `battery`, `symmetry`
  or a forbidden `no-fly arc`. Hover one to highlight it on the map; click an
  explored one to walk into that child. Most of the pruning lives here rather
  than in the node count — at n=7 the search entered 2,041 nodes but considered
  5,107 options, of which 1,722 died on the symmetry break alone and never
  became nodes at all.

### Controls

| Do this | Get this |
|---|---|
| Drag / wheel / pinch / `+` `−` `RST` / arrows / `0` | Pan and zoom, as on the flight replay |
| Double-click | Reset the view |
| Click a node | Select it and fill the inspector. The camera pans to it only if it was off-screen, and never changes zoom |
| Hover a node | Bound, incumbent and status |
| `Space` | Play / pause the search replay |
| `0.5× 1× 4× 16×` | Replay speed |
| Drag the scrubber | Seek. Nodes appear and disappear in expansion order |
| `←` `→` on the scrubber (`Shift` for a bigger step), `Home`, `End` | Seek by keyboard |
| `◀ improve` / `improve ▶` | Jump to the previous / next improvement |

The page opens with the whole tree drawn and the inspector on the node that
produced the answer. It honours `prefers-reduced-motion`.

### Watching the search find its first solution

By default `tree` warm-starts B&B from the best construction heuristic, so the
search often begins with an incumbent it never beats — and the tree then has no
improvements to jump between:

```bash
drp tree small.json --time 20 -o tree7.html --no-warm-start
```

At n=7 that goes from 2,041 nodes and 3 improvements to 2,245 nodes and 7, the
root's inspector reads `Incumbent here: none yet`, and the scrubber grows seven
green ticks to jump between. It is the better view if what you want to see is
the bound and the incumbent converging.

**Only do this on an instance B&B can get somewhere on.** Without a warm start
the search has to find its own first feasible solution, and on the n=14 worked
example it does not manage that inside 20 seconds at all:

```
search   : E=inf LB=605.3 gap=inf% (395336 nodes, 20.00s, timed out)
```

The page still renders — header incumbent `–`, gap `–`, both improvement buttons
disabled, every node's ramp colour taken from the bound range instead — but
there is no convergence story in it, because there was no convergence.

---

## 5. Convergence dashboard

```bash
drp dash inst.json --methods ga,sa,alns --time 5 -o dash.html
```

**For:** the question a table of best energies cannot answer — *how* each
metaheuristic got where it got, and whether it got there for a good reason. A
method that flatlines after half a second and a method that was still improving
when the clock stopped can report the same number and mean very different
things.

**Needs:** an **instance** JSON. Like `tree`, it runs the searches itself, with
tracing on.

**Cost** (n=14, 3 methods, `--time 5`):

| Command | Wall clock | Size |
|---|---|---|
| `--methods ga,sa,alns --time 5` | ~16 s | 716 KB |
| `--methods ga,sa,alns --time 5 --reference 10` | ~26 s | 717 KB |
| `--methods alns --time 3` | ~4 s | 429 KB |

Wall clock is just the sum of the per-method budgets (plus `--reference` if
given), so it is `methods × --time`. Size is dominated by the traces, and is
bounded: `--max-samples` (default 3000 per method) caps it regardless of how
many iterations the search runs.

### What is on the page

- **The main chart.** Every method's best-so-far, plus the *working* solution
  each one is actually holding, on one pair of axes.
- **A temperature panel** for SA and ALNS, with reheats marked.
- **A population panel** for GA: the mean and the spread of the population drawn
  as a band around the best. Watching that band close is watching the GA lose
  diversity; watching it stay open, as it does on this instance, is watching it
  not.
- **An operator panel** for ALNS — the reason for tracing ALNS at all. The
  destroy/repair weights are drawn as *shares of the roulette* over every weight
  update, stacked, so you can see the search learn. On the worked example
  `random` removal collapses to the 0.05 floor and stops being drawn at all,
  while `route` removal climbs to about 87% of draws. Only the final weights
  were ever reported before; this is the adaptation itself.
- **A scrubber** that moves one playhead across every panel at once, with each
  method's state at that moment in the panel beside it.

### Controls

| Do this | Get this |
|---|---|
| `Space`, or the play button | Play / pause the run |
| `0.5× 1× 4×` | Playback speed |
| Drag the scrubber | Move the playhead across every panel at once |
| `←` `→` (`Shift` for a bigger step), `Home`, `End` | Seek by keyboard |
| `seconds` / `steps` | Switch the x-axis |
| `fit best` / `fit all` | Whether the vertical range covers only the best-so-far curves, or the working solutions and the reference floor too |

The page honours `prefers-reduced-motion`, and reflows to one column on a phone.

### Two things it does deliberately, and why

**Wall-clock seconds is the default x-axis.** One GA generation evaluates
`pop_size` tours; one SA iteration evaluates one. Putting them on a shared step
axis silently claims those cost the same. The step axis is still there — it is
the honest axis for reading a single method's own behaviour — and when you
select it the chart heading says `not comparable across methods`.

**The vertical range fits the best-so-far curves, not everything.** An SA
working solution wanders far above every answer on the chart, and a range that
contains it squashes all three best-so-far curves into a band a few pixels tall,
which is the one thing the chart exists to show. Working solutions are clipped
instead; `fit all` restores the full range, and the page tells you which curves
it has clipped rather than letting the legend promise a line you cannot find.

### A floor to judge against

```bash
drp dash inst.json --methods ga,sa,alns --time 5 -o dash.html --reference 10
```

`--reference SECONDS` also runs B&B for that long and draws a floor across the
chart, turning "it converged" into "it converged to *this*". Two cases, and the
page distinguishes them because they mean different things:

* B&B **proved optimality** → the floor is the optimum, labelled `B&B optimum`.
  No metaheuristic can legitimately be below it, and a test asserts none is.
* B&B **did not** → the floor is its *dual bound*, labelled `B&B dual bound`.
  An unproven incumbent is not a floor and is never drawn as one; the dual bound
  genuinely is.

On the n=14 worked example B&B does not finish in 10 s, so you get:

```
bnb  : did not prove optimality in 10.0s; using its dual bound 605.33 as the floor
```

and the per-method gap to that bound appears in each panel (GA 44.7%, SA 50.2%,
ALNS 45.9%). Those are gaps to a *bound*, not to the optimum — the true optimum
is somewhere between 605 and 1095, and the gap to it is smaller than these
numbers. The page says which floor it is drawing so this cannot be misread.

### One run per method is an anecdote

The page says this itself, at the bottom, and it is worth repeating: `dash` runs
each method **once**, at one seed. A metaheuristic's spread across seeds is what
decides whether one method really beats another, and that is
`drp/eval/stats.py` (Wilcoxon, Friedman + Nemenyi, bootstrap CIs) via `drp bench`
and `drp compare` — not this view. Use the dashboard to understand a run's
*shape*; use the statistics to make a claim.

### Sampling

A 5-second SA run does around 8,700 iterations. Recording all of them would put
megabytes into the page for a curve a few thousand points wide, so traces are
**decimated**: every stride-th step is kept, and when the buffer fills, every
second sample is dropped and the stride doubles.

That matters more than it sounds. A curve truncated to its first N points shows
the opening of the search and nothing after it — the one useless shape for a
convergence plot. Decimation keeps a *uniform* sample of the whole run at all
times. Improvements and reheats are recorded separately and in full, so no
marker is ever dropped, and the page prints the stride it ended up with
(`every 4th sampled`).

Raise `--max-samples` for a denser curve and a bigger file; lower it for the
reverse.

---

## Parameters that change the output

### `drp generate`

| Flag | Default | Effect |
|---|---|---|
| `--n` | required | number of customers |
| `--drones` | required | fleet size, K |
| `--seed` | `1` | the instance's random seed — **and the flight replay's basemap** |
| `--zones N` | `0` | N polygonal no-fly zones (the detour model) |
| `--nofly F` | `0.0` | forbid the longest F of edges outright (the edge model) |
| `--name` | `instance` | instance name, used in page titles |
| `-o` | `instance.json` | output path |

Two things worth knowing:

**`--zones` is what makes the replay interesting.** Polygonal zones do not forbid
arcs, they lengthen them: the distance matrix becomes the obstacle-avoiding
shortest path, so routes bend visibly around the magenta restricted areas
instead of cutting through, and the "why this route" panel gets a real
straight-line-versus-flown distance to report. Without zones the replay is a set
of straight lines. `--zones 2` is enough; `--zones 3` or `4` on a small instance
gives a lot of detouring.

**`--seed` also seeds the replay's basemap.** The river, the road network, the
land-use polygons and the district labels are all generated from a seed derived
from the instance — customer count, depot position, zone count and `--seed`
itself. The same instance therefore always draws the same city, and two
different seeds draw two different ones. This is why a figure regenerated later
looks identical.

`--nofly` and `--zones` are separate models and **`--zones` wins**: with
`--zones N` for N > 0, `--nofly` is ignored.

### `drp show`

| Flag | Default | Applies to |
|---|---|---|
| `-o` | `routes.png` | the static plot (always written) |
| `--instance` | required | all |
| `--animate PATH` | off | GIF/MP4; format from the extension |
| `--web PATH` | off | the flight replay |
| `--title` | instance name and energy | the plot, the GIF and the page |
| `--frames` | `160` | `--animate` only |
| `--fps` | `20` | `--animate` only |
| `--separation` | 3% of the field span | `--animate` and `--web` |
| `--vision` | off | `--web` only |
| `--vision-time` | `10.0` | the `--vision` search budget, seconds |
| `--max-nodes` | `20000` | trace records kept for `--vision` |

### `drp tree`

| Flag | Default | Effect |
|---|---|---|
| `--time` | `20.0` | search budget, seconds |
| `-o` | `tree.html` | output path |
| `--max-nodes` | `4000` | recorded nodes. Bounds the **recording**, never the search |
| `--title` | instance name | page title |
| `--solution PATH` | off | also write the solution B&B found |
| `--no-warm-start` | off | start with no incumbent |

### `drp dash`

| Flag | Default | Effect |
|---|---|---|
| `--methods` | `ga,sa,alns` | which metaheuristics to run; any subset |
| `--time` | `5.0` | seconds **per method** |
| `--seed` | `1` | seed for every method |
| `-o` | `dash.html` | output path |
| `--max-samples` | `3000` | samples kept per method. Bounds the **recording**, never the search |
| `--reference SECONDS` | `0` (off) | also run B&B this long and draw its optimum, or failing that its dual bound, as a floor |
| `--title` | instance name | page title |

`dash` supports `ga`, `sa` and `alns` only. `greedy` is a construction heuristic
with nothing to converge, and `bnb` has its own view (`drp tree`); ask for either
and it exits with a message rather than drawing an empty panel.

### Still Python-API only

Two things the CLI does not reach, for want of a sensible flag rather than
because they are unsupported:

- **`animate_routes(..., frames=…, fps=…, separation=…, title=…)`** is fully
  exposed now (`--frames`, `--fps`, `--separation`, `--title`). Nothing is
  missing here.
- **`render_playback_html(..., vision=…)`** takes a payload from
  `drp.viz.treedata.build_vision_data`, which lets you supply a trace from a
  search *you* configured rather than the one `--vision` runs for you. The CLI
  always runs its own.
- **`solve_ga` / `solve_sa` / `solve_alns`** take `trace=True` and
  `trace_max_samples`, so you can trace a run you configured yourself — a
  different temperature schedule, a different segment length — rather than the
  one `dash` runs for you, and hand the traces to `render_dashboard_html`
  through `drp.viz.dashdata.MethodRun`.
- **`build_playback_data`**, **`build_tree_data`** and **`build_dashboard_data`**
  return the raw dicts, if you want to render the payload some other way:

```python
from drp.exact.bnb import solve_bnb
from drp.instances import load_instance
from drp.meta.construct import best_construction
from drp.viz.treedata import build_tree_data
from drp.viz.webtree import render_tree_html

inst = load_instance("inst.json")
res = solve_bnb(inst, time_limit=20.0, warm_start=best_construction(inst),
                trace=True, trace_max_nodes=4000)
render_tree_html(inst, res, "tree.html", title="my title")
payload = build_tree_data(inst, res)      # the same dict, unrendered
```

---

## Troubleshooting

**The HTML page says "This page could not load GSAP".** You are offline, or
behind something that blocks cdnjs.cloudflare.com. Reconnect and reload — the
data is already in the file, only the library is missing.

**`--animate flight.mp4` fails.** MP4 goes through `ffmpeg`, which is not a
Python dependency. Install it, or use `.gif`.

**`tree.html` is enormous.** Lower `--max-nodes`. It costs roughly 500 bytes per
recorded node.

**The tree explorer says the trace was capped and I want the whole thing.** Use a
smaller instance. B&B's tree grows very fast: 2,041 nodes at n=7, 13,373 at n=8,
183,341 at n=10. `--max-nodes 20000` covers n=8 completely.

**Solver Vision shows nothing for most drones.** The B&B search never reached
those parts of the solution — likely because it timed out, or because the
solution came from a metaheuristic and B&B went elsewhere. Give it more
`--vision-time`, use a smaller instance, or replay B&B's own solution
(`drp tree … --solution bnbsol.json`). The page reporting a shortfall is it
working correctly, not failing.

**`dash.html` is large.** Lower `--max-samples`. At the default 3000 per method
each traced method costs a few hundred KB.

**A method shows `Improvements on the start: 0`.** That is a result, not a bug:
the method never beat the solution it was handed. SA does this on larger
instances — see `PROGRESS.md` §2.4 for the measurements and the likely cause.

**`drp: command not found`.** Run `pip install -e .` from the repository root.
