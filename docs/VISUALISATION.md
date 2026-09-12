# Visualising a run

Six views, all reachable from the command line:

| View | Command | Output |
|---|---|---|
| Static route plot | `drp show … -o routes.svg` | PNG, SVG, PDF or EPS — the extension decides |
| Animated playback | `drp show … --animate flight.gif` | GIF (or MP4) |
| Interactive flight replay | `drp show … --web flight.html` | one self-contained HTML file |
| B&B search-tree explorer | `drp tree … -o tree.html` | one self-contained HTML file |
| Convergence dashboard | `drp dash … -o dash.html` | one self-contained HTML file |
| Interactive planner | `drp serve` | a local web app -- place stops, solve, see the other three |

All six take `--theme` (the planner as a startup flag, the other five as a
per-command one). The default, `safe`, is the colour-blind-safe theme;
`--theme chart` is the original aeronautical-chart palette. See
[Themes](#themes) below.

This document is meant to be driven start to finish from an empty directory.
Every command below was executed before it was written down; the timings and
file sizes are from those runs, on an ordinary laptop.

For *why* the views look the way they do, see `PROGRESS.md` §2.2, §2.4 and
§2.5.

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
| `routes.png` | 113 KB | the static plot (`-o routes.svg` gives 40 KB of vector instead) |
| `flight.html` | 124 KB | the interactive replay |

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
drp show sol.json --instance inst.json -o routes.svg
drp show sol.json --instance inst.json -o routes.pdf
```

**For:** a figure for a report or a slide. This is the one that goes in the
paper.

**Needs:** a solution JSON and its instance JSON.

**Cost:** about 1 second. Sizes at n=14, same figure:

| `-o` | Size | What it is |
|---|---|---|
| `routes.png` | 113 KB | 150 dpi raster |
| `routes.svg` | 40 KB | vector, opens in a browser or Illustrator |
| `routes.pdf` | 14 KB | vector, what `pdflatex` embeds without conversion |
| `routes.eps` | 29 KB | vector, for a journal that still asks for it. PostScript has no transparency, so matplotlib warns and renders the no-fly zones' 14% fill opaque — use PDF unless something insists on EPS |

One matplotlib figure: depot, customers, one colour *and one dash pattern and
one marker shape* per drone, routes drawn along the path actually flown (bent
around any polygonal no-fly zone, not straight through it), and the total energy
in the title. `-o` is required in the sense that it always writes something — it
defaults to `routes.png` — so `show` never runs without producing the static
plot, even when you only wanted `--web`.

### Vector output

**The extension picks the format.** There is no `--format` flag and there does
not need to be one: matplotlib reads the suffix, and `save_figure` only has to
stop forcing a raster dpi on a vector target. `.svg`, `.svgz`, `.pdf`, `.eps`
and `.ps` are the vector suffixes; anything else is rasterised at 150 dpi.

Two consequences worth knowing:

**Vector output is reproducible**, which took two fixes and neither is
matplotlib's default. It stamps a creation date into SVG and PDF, so both are
stripped. And the SVG backend salts its internal element ids
(`clip-path="url(#pd8f8ba3302)"`) *per process*, so two identical figures from
two runs differed in every id; `svg.hashsalt` pins it. With both, regenerating a
figure from the same inputs gives the same bytes, and "did this figure change?"
becomes a question the repository can answer.

**Vector output showed that the figures' type was too small.** A figure drawn
7.5 inches wide and placed at `0.65\textwidth` — 4.09 inches, in this report's
A4 geometry — is shrunk to 0.55 of its size by LaTeX, taking 11 pt text down to
6 pt and an 8 pt customer label down to 4.4 pt. At 150 dpi that was invisible: a
4 pt label rasterises to a grey smudge that reads as "fine print" and nobody
looks closer. In vector it is crisp and unmistakably too small.

So `plot_routes` and the rest now take `placed_at` — the fraction of
`\textwidth` the figure will be printed at — and size type and strokes so they
land at 9 pt headings, 8 pt ticks and 7 pt annotations *on the page*.
`generate_figures.py` holds one table of those fractions, `PLACED_AT`, which has
to be kept in step with the `\includegraphics[width=…]` calls in
`report/report.tex`. `drp show` passes nothing, because a figure you asked for
by name is not going into that report.

### TikZ

Not done, deliberately, and this is the place to say why rather than half-adding
it. Over PDF, TikZ buys exactly one thing: figure text set in the document's own
font, at the document's own size, by the same typesetter. It costs a
matplotlib-to-TikZ dependency, a build that can now fail inside LaTeX rather
than inside Python, and tens of thousands of generated lines of `.tex` per
data-heavy figure — `fig_comparison` alone draws 60 bars. The font argument is
also weaker than it sounds now that the figures are sized for where they land.
If the report ever does need figure text to match exactly, the cheap half of
that is matplotlib's own `pgf` backend, which needs no new Python dependency;
try it before reaching for TikZ.

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

**Cost:** ~2 s, ~124 KB at n=14. Both are nearly flat in instance size; the page
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
| `--methods ga,sa,alns --time 5` | ~17 s | 702 KB |
| `--methods ga,sa,alns --time 5 --reference 10` | ~26 s | 719 KB |
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

## 6. Interactive planner

```bash
drp serve
```

**For:** trying a what-if without hand-writing JSON first -- place stops on a
map, set the fleet, solve, and see the other three views on the result,
without touching a text editor.

**Needs:** nothing on disk. It is a local web app, not a file-producing
command: `drp serve` starts a small HTTP server on `127.0.0.1`, prints its
URL, and opens it in a browser.

```
drp planner: http://127.0.0.1:8323/
Ctrl+C to stop
```

Everything else in this document produces a *file*; this is the one view
that is a running program. It writes nothing into the directory it was
launched from -- every rendered result lives under a private temporary
directory the server owns and serves back at `/results/<id>/...`, cleaned up
when the process exits. `--no-browser` skips the automatic open (for
scripted use); `--port` picks a fixed port instead of a free one; `--theme`
works the same as everywhere else.

### The architecture, briefly

The browser only ever talks to this server. Every solver call happens here,
in Python, exactly as `drp solve`/`drp tree`/`drp dash` call it -- nothing
was ported to JavaScript, and the project keeps exactly one copy of every
algorithm. Placing stops and clicking Solve builds an ordinary
`drp-instance/v1` document in the browser and posts it; the server loads it
through the same `instance_from_dict` a file on disk goes through, so a
malformed instance fails exactly the same way. The result pages are the
existing `render_playback_html` / `render_dashboard_html` / `render_tree_html`
functions, called unmodified and embedded in the planner page as iframes --
nothing about their pinned, tested behaviour changes because a browser is
asking for them instead of a shell.

### Controls

**The map.** Reuses the flight replay's pan/zoom camera -- drag to pan, wheel
to zoom, `+`/`−`/`RST` buttons, arrow keys, `0` and double-click to reset --
trimmed to planar coordinates only and without pinch-zoom (this version does
not build geodesic instances; see "What this version does not do" below).
Click empty ground to add a stop; drag an existing stop to move it; click a
stop to remove it; **drag the depot itself to relocate the starting
location** -- it is not fixed. The sidebar lists every stop with its
coordinates and an editable demand field, and the fleet card sets drone
count, payload and battery.

It is not a blank grid: the ground layer draws the same invented aeronautical
chart the flight replay draws for a synthetic instance -- a river, a radial
road network centred on the depot, built-up blobs, parks and district names
-- ported from `playback_template.html` and reseeded from the same two things
that change here (how many stops there are, and where the depot sits), so the
placement map and the solved replay read as one city rather than two
different-looking tools. It regenerates when a stop is added or removed, and
once when a depot drag releases -- not on every pointer movement, since
rebuilding a few hundred SVG nodes on every frame of a drag would make the
drag itself feel laggy.

**Solve.** Runs ALNS at a fixed 5-second budget -- the "short default budget"
the roadmap asks for -- and shows a loading screen with the real elapsed time
against that budget while it waits. On success the flight replay appears
embedded below, scrolled into view automatically, sized to its own actual
content height rather than boxed into a fixed panel with a second,
inner scrollbar -- it is a full page, built for a whole browser tab, and
looks like one here too. The dashboard and tree tabs do the same once run.

**The other two tabs** -- convergence dashboard and search tree -- start
empty with a *Run* button and a quick/thorough budget switch (dashboard: 3 s
or 8 s per method; tree: 10 s or 25 s), computed only when asked for, each
with its own honest countdown. The tree tab shows the same "complete only for
roughly 8 stops or fewer" caveat as `drp tree` itself before you wait on a
timed-out one.

### Reading the countdown

**It is real elapsed time against the real budget the request was sent
with, never a fabricated step.** The solve is genuinely synchronous -- the
server does not return until the solver does -- so the page cannot show true
progress *inside* the solve; what it can show, honestly, is how long the
wait has actually been running, which is what it shows. The metaheuristic
tabs (the first solve, and the dashboard) label this `elapsed / budget`
because they run to their budget. The tree tab labels it "up to Ns elapsed"
because B&B can finish early by proving optimality, and a plain countdown
would imply a wait that might not happen.

### Limits

| | |
|---|---|
| Stops | 2 to 60 (`drp.app.server.MIN_STOPS`/`MAX_STOPS`) |
| Drones | 1 to 12 (`MAX_DRONES`) |
| Concurrency | one solve at a time -- a second request while one is running gets a `409`, not a queue |

The lower stop bound is not a product choice: `drp.meta.alns`'s destroy step
samples at least 2 customers off the giant tour (§5.2's "absolute floor of
2"), which is an uncaught `ValueError` on a 1-customer tour. No committed
benchmark instance had ever been that small, so nothing had exercised it
until the planner made a 1-stop instance reachable for the first time --
fixed at that new boundary rather than by touching the solver.

**Impossible inputs get a message that names the stop, not a broken page.**
When a solve returns no solution at all -- a stop's demand above the fleet's
payload, or a stop no drone can reach on one battery charge even alone -- the
server scans the customers in order and reports the first one that makes the
instance unsolvable, by name, instead of a bare "no solution found". Where a
solution does exist but fails some other way, the message comes straight off
`feasibility_certificate`'s own `reason`, the same certificate every
`drp-solution/v1` file carries.

### What this version does not do

Stated plainly, per the roadmap's own scoping: no real-geography toggle --
the plane is a plain 100×100 square with an *invented* city drawn on it, the
same way a synthetic instance gets one in the flight replay, not the
Pontianak geodesic instance or its OSM basemap -- no drawing no-fly zones, no
Solver Vision toggle on the embedded replay, and no live progress streaming
while a solve runs. The brief rules the last one out deliberately; "watching
the algorithm" is what the tree explorer and convergence dashboard are *for*,
as a replay afterwards, not a thing to fake here. The camera code is a
copied-and-trimmed version of the flight replay's, not a shared module --
pinch-zoom (touch) was trimmed along with the geodesic branch.

**A found-by-screenshot bug, worth recording because the fix generalises.**
The first working version of the basemap port left every district-name label
positioned at the SVG origin instead of its collision-checked spot -- the
world-space *plotting* code was ported faithfully, but the actual
`x`/`y` assignment lives in a separate step in the flight replay (a `transform`
rewritten per zoom, for counter-scaling), which was dropped rather than
adapted. The result was several place names stacked on top of each other,
reading as garbled overlapping text -- invisible in the automated tests
(nothing asserted on label position) and obvious in one screenshot. Fixed by
setting `x`/`y` directly at creation, which this page can do because its
labels are terrain and do not need to hold a constant screen size the way the
replay's do. `tests/browser/test_page_planner.py` now asserts every ground
label has a distinct position.

### Testing it

`tests/test_server.py` drives the server directly over HTTP (no browser): a
valid instance solves, an oversized or undersized one is refused, an
infeasible one names the stop, malformed JSON is a `400` and not a crash,
`/results/` cannot be walked outside its own directory, and a concurrent
solve is refused rather than queued silently.
`tests/browser/test_page_planner.py` (7 tests) is the one browser-test file
of four that drives a real running server instead of a `file://` page:
placing stops through to a rendered replay with the right customer count, the
countdown never showing anything but real elapsed/budget, an infeasible
placement surfacing its reason, no horizontal overflow at 430 px, the ground
layer actually drawing terrain with every label at a distinct position,
dragging the depot changing what gets solved, and the embedded replay
growing to its real content height rather than carrying its own internal
scrollbar.

---

## Themes

Every view takes `--theme`. Two ship:

| `--theme` | What it is |
|---|---|
| `safe` (default) | Colour-blind safe, and measured for it |
| `chart` | The original aeronautical-chart palette, unchanged |

`DRP_VIZ_THEME=chart` sets the default for a shell; `--theme` beats it. From
Python, every drawing entry point takes `theme=` — a name or a
`drp.viz.theme.Theme` — so two themes can be rendered side by side in one
process without touching global state.

```bash
drp show sol.json --instance inst.json -o routes.svg --theme chart
drp tree inst.json --time 20 -o tree.html --theme chart
drp dash inst.json --time 5 -o dash.html --theme chart
DRP_VIZ_THEME=chart drp show sol.json --instance inst.json -o routes.png
```

### Why the old palette had to go, with the numbers

"Colour-blind safe" is a claim until something measures it, so `drp/viz/cvd.py`
implements the standard simulation — Viénot, Brettel & Mollon (1999) for
protanopia and deuteranopia, Brettel, Viénot & Mollon (1997) for tritanopia —
and CIE76 dE\*ab for the distance. `tests/test_viz_theme.py` runs both over
every colour either theme names.

`chart`'s six route colours are `#2E75B6 #C0504D #4E8542 #8064A2 #F79646
#4BACC6`. The closest pair in that set, simulated:

| Vision | Closest pair, dE | Which pair |
|---|---|---|
| normal | 26.2 | blue / purple |
| protanopia | 9.4 | blue / purple |
| **deuteranopia** | **7.8** | **red / green** |
| tritanopia | 16.4 | green / purple |

A dE of 7.8 is "the same colour with a bad print". `safe` scores **29.5** at its
worst pair across all three deficiencies. `results/fig_theme.png` draws both
palettes as each kind of colour vision receives them, and is regenerated by
`generate_figures.py` alongside everything else.

The same problem was in the pages: the flight replay used green for delivered
and red for a separation breach, and the dashboard's method colours were
purple / red / blue, whose red and blue collapse onto each other under
protanopia.

### The finding nobody expected: the bound ramp

The tree explorer's lower-bound ramp — teal → amber → magenta — was expected to
be close to safe already. It is not, and the failure is worse than a confusable
pair. A *sequential* ramp has to be monotone in perceived distance from its own
start, or a high value looks like a low one. Sampled at nine points and
simulated:

| Vision | dE from the start, first → last |
|---|---|
| normal | 0 → 12 → 27 → 43 → **60** → 56 → 57 → 65 → 76 |
| protanopia | 0 → 11 → 23 → 35 → **46** → 31 → 17 → 14 → 28 |
| deuteranopia | 0 → 13 → 28 → 43 → **58** → 45 → 30 → 15 → **9** |
| tritanopia | 0 → 8 → 19 → 32 → **50** → 46 → 51 → 56 → 59 |

Read the deuteranopia row: the ramp's *far end* lands dE 9 from its near end
while its middle is 58 away. It folds back on itself, so the highest bounds are
drawn in the same colour as the lowest — in the one view where the bound is the
whole point. And it is not monotone for **any** of the four, normal vision
included; the deficiencies only make an existing flaw severe.

`safe`'s ramp is navy → violet → amber:

| Vision | dE from the start, first → last |
|---|---|
| normal | 0 → 5 → 11 → 17 → 24 → 36 → 54 → 74 → 93 |
| protanopia | 0 → 4 → 9 → 14 → 18 → 35 → 54 → 74 → 93 |
| deuteranopia | 0 → 6 → 11 → 18 → 25 → 45 → 66 → 87 → 107 |
| tritanopia | 0 → 4 → 12 → 20 → 29 → 38 → 47 → 56 → 63 |

Monotone under all four, spanning at least dE 63.

### Colour is never the only channel

No palette helps a monochromat, and none survives a fax. So every theme also
carries a **dash pattern**, a **marker shape** and a **bar hatch**, indexed on
the same number as the colour:

- **Routes** get a dash pattern in the static plot, the GIF and the flight
  replay — and the manifest row's spine repeats it, so a row and its route are
  matched by shape as well as by hue.
- **Methods** get a dash pattern and a marker in every figure and on the
  dashboard, whose legend rules are drawn as tiny SVGs so they carry the exact
  pattern the curve does.
- **Node statuses** in the tree explorer get a ring dash pattern, which matters
  more there than anywhere else because the fill under the ring is itself a
  colour from the bound ramp.
- **Bars** get a hatch, which is what makes `fig_comparison` readable in
  greyscale.
- **Delivered** is a filled disc with a tick, **pending** an empty outline,
  **breached** a dashed ring with the numbers beside it. Three shapes, not three
  colours.

The second channel is identical in both themes, so switching theme changes only
the colour and a figure's *shapes* stay comparable between the two.

### What the theme does not fix

Six route colours, five semantic ones and a sequential ramp cannot all be
mutually far apart at 3:1 contrast on a cream page. The tightest route-versus-
semantic pair in `safe` is dE 11.2 — a dark red route against the crimson a
breach flashes in. That is a stated limit, not an oversight, and it is the
reason the shapes above exist: the two are drawn as different *kinds* of mark, a
stroke against a dashed ring with a labelled banner.

------

## Testing the pages

Until roadmap §2.5, none of the JavaScript on the three HTML pages was covered
by anything. `tests/test_viz_web.py`, `test_viz_tree.py` and `test_viz_dash.py`
pin the *payloads* — the geometry, the derived dual-bound series, the axis
limits — and every one of them passes against a page that throws on load and
renders nothing. Every bug §2.2 and §2.4 record was found by driving the pages
in a browser by hand.

`tests/browser/` is that, automated. 67 tests across the three pages, plus
seven more covering the planner (§2.1, added later — see its own section
above), 74 in total:

```bash
pip install -e ".[dev,browser]"
playwright install chromium

pytest -q -m browser        # ~50 s
```

They skip, with a message, if Playwright or Chromium is missing — so a checkout
without them is not silently uncovered, it says so.

**They are marked `slow` as well as `browser`**, which keeps `pytest -q -m "not
slow"` — the fast subset — at the same ~2.5 minutes it was. `pytest -q` runs
everything.

### What they assert

Beyond "it rendered": that no page error or console error was raised, that the
GSAP guard did not fire, that the panels are populated rather than empty shells,
that the numbers on the page are the numbers in the payload that produced it,
that play advances and scrubbing seeks and selection fills the inspector, and
that nothing overflows sideways at 430 px.

And, specifically, one test per bug found by hand, named after it:

| Test | The bug it would have caught |
|---|---|
| `test_no_uncaught_errors_anywhere_on_load` | The three temporal-dead-zone crashes. They threw *and* left a partly built page, so counting elements was not enough — only watching `pageerror` catches them |
| `test_next_improvement_wraps_instead_of_doing_nothing` | "Next improvement" was dead on arrival, because the page opens at the end of the search where there is no next improvement |
| `test_fit_best_does_not_squash_the_curves_into_a_band` | The y-range contained SA's working solution, so the three curves the chart exists to compare occupied ~2% of the plot height instead of ~79% |
| `test_home_does_not_leave_every_readout_empty` | Every readout said `–` at `Home`, because the x-domain began at 0 and the first sample lands a few milliseconds in |
| `test_edges_and_nodes_are_in_separate_layers` | The tree rendered as a black mass, because each node's edge lived in that node's group and painted over every earlier circle |
| `test_seeking_backwards_un_fires_events` | The documented promise that seeking back un-fires events, which nothing enforced |
| `test_the_rail_is_height_bound_to_the_map_on_desktop` | The map painted over the manifest, because `aspect-ratio` fed the panel's height back into its width |
| `test_the_mini_map_is_not_hidden_behind_a_scrollbar` | The tree explorer's rail was height-bound the wrong way, hiding the mini map |

### Three things the harness does, and why

**GSAP is served from a local cache, not the CDN.** The pages fetch it from
`cdnjs.cloudflare.com`, which makes a network hiccup look like a test failure.
The first run downloads it to `tests/browser/.cache/` (gitignored); after that
it is served from disk through a Playwright route. Fonts are fulfilled empty —
they are not under test, and waiting on them is the slowest part of a load.

**Pages load with `prefers-reduced-motion: reduce`.** All three honour it by
resolving every transition instantly, so the DOM reaches its final state on the
first frame and no assertion races an intro tween. One test loads with motion on
instead and asserts it settles in the same place, which is the only thing that
actually checks the reduced-motion claim this document makes.

**The fixtures are tiny and rendered once per session.** The solvers are the
slow part, not the browser. The tree fixture runs `--no-warm-start` on purpose:
without it the search often has no improvements, and then the button whose
deadness is being tested has nothing to do.

**The planner's tests navigate to a live server instead of a `file://` page**
— the one structural difference, since it is the one view that is a running
program rather than a file. `planner_server` (in `tests/browser/conftest.py`)
starts a real `drp.app.server` instance on `127.0.0.1` with a free port,
session-scoped like the other page fixtures.

### In CI

`.github/workflows/ci.yml` runs them in their own job, on **every push and every
pull request** rather than only on `main`. The whole reason the job exists is
that JavaScript regressions are invisible in review; deferring it to `main`
means a pull request can break a page and merge green.

Honest cost: about 40 s to install the package, 25 s for Chromium on a cache hit
(90 s cold, once per Playwright version) and 60–75 s for the tests — so roughly
**2 minutes warm, 3 cold**. It runs in parallel with the existing jobs, so it
adds wall-clock time only if it becomes the longest of them, which it does not.

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
| `-o` | `routes.png` | the static plot (always written); `.svg`/`.pdf`/`.eps` give vector |
| `--theme` | `safe` | the plot, the GIF and the page |
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
| `--theme` | `safe` | colour theme; see [Themes](#themes) |

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
| `--theme` | `safe` | colour theme; see [Themes](#themes) |

`dash` supports `ga`, `sa` and `alns` only. `greedy` is a construction heuristic
with nothing to converge, and `bnb` has its own view (`drp tree`); ask for either
and it exits with a message rather than drawing an empty panel.

### `drp serve`

| Flag | Default | Effect |
|---|---|---|
| `--host` | `127.0.0.1` | bind address; stays loopback, this is not for exposing on a network |
| `--port` | `0` (a free port) | fixed TCP port instead |
| `--no-browser` | off | do not open a browser window (scripted use) |
| `--theme` | `safe` | colour theme for every page it renders; see [Themes](#themes) |

Unlike the other five, `serve` takes no instance and no output path — the
instance is whatever gets placed in the browser, and the output is a running
server, not a file.

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

**The planner says "place at least 2 delivery stops".** Not a UI quirk: a
1-stop instance crashes `drp.meta.alns`'s destroy step (it samples 2
customers off the giant tour), so the server refuses it before it ever
reaches a solver. Add a second stop.

**The planner says a solve is already running.** One solve at a time, by
design — the server holds a single lock across the first solve and the
dashboard/tree tabs alike. Wait for the current one to finish.

**A method shows `Improvements on the start: 0`.** That is a result, not a bug:
the method never beat the solution it was handed. SA does this on larger
instances — see `PROGRESS.md` §2.4 for the measurements and the likely cause.

**`drp: command not found`.** Run `pip install -e .` from the repository root.
