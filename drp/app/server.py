"""A small local HTTP server for the interactive planner (roadmap §2.1).

`drp serve` starts this, opens a browser, and lets someone place delivery
stops on a map, configure the fleet, and solve -- without touching a text
editor or the command line again. The browser only ever talks to this server;
every solver runs here, in Python, unchanged (`drp.eval.runner.solve_one` for
the first look, `solve_ga`/`solve_sa`/`solve_alns`/`solve_bnb` directly for the
dashboard and tree tabs -- the same calls `drp dash` and `drp tree` make). The
three existing self-contained pages (`render_playback_html`,
`render_dashboard_html`, `render_tree_html`) are reused unmodified: each solve
writes its result page into a private subdirectory of this server's own temp
output root, and this server serves that directory back as static files. That
sidesteps touching three modules with pinned, tested behaviour just to add a
"return a string instead of writing a file" mode nothing else needs.

Deliberately minimal: stdlib `http.server` only, no new dependency. Bound to
loopback by default, one solve at a time (a single lock covers the first ALNS
solve and the dashboard/tree tabs alike, since they are all solver runs on a
single-user local tool), and `/results/<id>/...` can only ever resolve inside
this server's own output directory.
"""
from __future__ import annotations

import json
import mimetypes
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlsplit

from drp.core.energy import route_energy
from drp.core.feasibility import feasibility_certificate
from drp.core.instance import DRPInstance
from drp.eval.runner import solve_one
from drp.instances.io import instance_from_dict
from drp.viz.theme import resolve as resolve_theme
from drp.viz.webdash import render_dashboard_html
from drp.viz.webplayback import render_playback_html
from drp.viz.webtree import render_tree_html

#: Caps enforced here as well as in the page's own form validation -- a
#: request is never trusted just because the page that built it validated it.
#: `MIN_STOPS = 2` is not a product choice: `drp.meta.alns`'s destroy step
#: samples at least 2 customers off the giant tour (roadmap §5.2's "absolute
#: floor of 2"), which is a `ValueError` -- not caught anywhere -- on a
#: 1-customer tour. No committed benchmark has ever been that small, so
#: nothing upstream exercises it; fixing it here, at the boundary that newly
#: makes n=1 reachable, keeps every solver's behaviour on every existing
#: instance exactly as it was (the brief's own rule).
MIN_STOPS = 2
MAX_STOPS = 60
MAX_DRONES = 12
MAX_BODY_BYTES = 2_000_000

#: "Metaheuristics run to their time budget, so the loading screen can show
#: real elapsed/budget time" (roadmap §2.1). These are exactly the numbers the
#: page's countdown is honest about, not decoration.
SOLVE_BUDGET = 5.0
DASH_BUDGETS = {"quick": 3.0, "thorough": 8.0}
TREE_BUDGETS = {"quick": 10.0, "thorough": 25.0}
TREE_MAX_NODES = 8000
#: B&B's tree is only complete for small instances; see docs/VISUALISATION.md.
TREE_COMPLETE_CEILING = 8

TEMPLATE_PATH = (Path(__file__).resolve().parent.parent / "viz" / "web"
                 / "planner_template.html")
DATA_TOKEN = "__DRP_PLANNER_DATA_JSON__"

#: Everything the page needs to start empty: a 100x100 planar working area
#: (this version is planar-only -- real geography is a stretch goal, not
#: built here), a depot fixed at its centre, and fleet defaults sized so a
#: handful of stops anywhere in the square are actually reachable (round trip
#: to the farthest corner is ~366 energy against a 450 battery).
DEFAULTS: Dict[str, Any] = {
    "plane": {"xmin": 0.0, "xmax": 100.0, "ymin": 0.0, "ymax": 100.0},
    "depot": [50.0, 50.0],
    "fleet": {"n_drones": 4, "payload": 20.0, "battery": 450.0},
    "energy": {"alpha": 1.0, "beta": 0.3},
    "demand_default": 2.0,
    "limits": {"min_stops": MIN_STOPS, "max_stops": MAX_STOPS, "max_drones": MAX_DRONES},
    "budgets": {"solve": SOLVE_BUDGET, "dash": DASH_BUDGETS, "tree": TREE_BUDGETS},
    "tree_complete_ceiling": TREE_COMPLETE_CEILING,
}


class PlannerError(Exception):
    """Carries the HTTP status a request should fail with."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class Session:
    """One instance that has been solved at least once.

    Kept server-side, keyed by an opaque id, so the dashboard and tree tabs
    can run other solvers against the *same* instance without the browser
    re-posting every stop.
    """

    instance: DRPInstance
    created: float = field(default_factory=time.time)


class PlannerState:
    """Everything one running server needs, held off the handler instances
    (`BaseHTTPRequestHandler` makes a new one per request)."""

    def __init__(self, output_root: Path, theme: Optional[str] = None):
        self.output_root = output_root
        self.theme = resolve_theme(theme)
        #: One solve (of any kind) at a time -- the brief's own rule, and the
        #: honest reason a countdown never has to account for a concurrent run.
        self.lock = threading.Lock()
        self.sessions: Dict[str, Session] = {}
        self.template = TEMPLATE_PATH.read_text(encoding="utf-8")

    def page(self) -> str:
        data = dict(DEFAULTS)
        data["theme"] = self.theme.to_dict()
        # `</` would otherwise let a string field break out of the <script>.
        payload = json.dumps(data).replace("</", "<\\/")
        return self.template.replace(DATA_TOKEN, payload)

    def new_session(self, inst: DRPInstance) -> str:
        sid = uuid.uuid4().hex
        (self.output_root / sid).mkdir(parents=True, exist_ok=True)
        self.sessions[sid] = Session(instance=inst)
        return sid

    def session_dir(self, sid: str) -> Path:
        d = self.output_root / sid
        d.mkdir(parents=True, exist_ok=True)
        return d


# ---------------------------------------------------------------------------
# request handling, factored out of the HTTP plumbing so it is unit-testable
# without spinning up a socket
# ---------------------------------------------------------------------------
def _instance_from_payload(payload: Any) -> DRPInstance:
    if not isinstance(payload, dict):
        raise PlannerError(400, "request body must be a JSON object")

    customers = payload.get("customers")
    if not isinstance(customers, list) or len(customers) < MIN_STOPS:
        raise PlannerError(400, f"place at least {MIN_STOPS} delivery stops")
    if len(customers) > MAX_STOPS:
        raise PlannerError(400, f"at most {MAX_STOPS} stops (got {len(customers)})")

    fleet = payload.get("fleet")
    n_drones = fleet.get("n_drones") if isinstance(fleet, dict) else None
    if not isinstance(n_drones, int) or not (1 <= n_drones <= MAX_DRONES):
        raise PlannerError(400, f"drones must be an integer between 1 and "
                                f"{MAX_DRONES} (got {n_drones!r})")

    try:
        return instance_from_dict(payload)
    except PlannerError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise PlannerError(400, f"malformed instance: {exc}") from None


def _first_impossible_stop(inst: DRPInstance) -> Optional[Dict[str, Any]]:
    """Name the first stop that makes this instance unsolvable outright.

    Used only when construction fails completely (`solve_one` returns no
    solution at all) -- the normal case reads the reason off the solution's
    own feasibility certificate instead, per the brief's own instruction.
    """
    for i in range(1, inst.N):
        if inst.demand[i] > inst.payload + 1e-9:
            return {"id": i,
                    "reason": (f"stop {i} needs {inst.demand[i]:g} of payload, "
                               f"more than the fleet's capacity of "
                               f"{inst.payload:g}")}
        e = route_energy(inst, [i])
        if e > inst.battery + 1e-9:
            return {"id": i,
                    "reason": (f"stop {i} is unreachable on one battery charge "
                               f"-- a round trip there and back alone costs "
                               f"{e:.1f}, against a {inst.battery:g} capacity")}
    return None


def handle_solve(state: PlannerState, body: bytes) -> Dict[str, Any]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PlannerError(400, f"malformed JSON: {exc}") from None

    inst = _instance_from_payload(payload)

    if not state.lock.acquire(blocking=False):
        raise PlannerError(409, "a solve is already running -- wait for it "
                               "to finish")
    try:
        res = solve_one(inst, "alns", seed=1, time_limit=SOLVE_BUDGET)
    finally:
        state.lock.release()

    sid = state.new_session(inst)

    if res.solution is None:
        bad = _first_impossible_stop(inst)
        reason = (bad["reason"] if bad else
                  "no feasible solution was found for this fleet and these "
                  "stops")
        return {"ok": True, "id": sid, "feasible": False, "reason": reason,
                "stop": (bad["id"] if bad else None), "budget": SOLVE_BUDGET}

    cert = feasibility_certificate(inst, res.solution)
    outdir = state.session_dir(sid)
    render_playback_html(inst, res.solution, outdir / "flight.html",
                         title="planner solve", theme=state.theme)
    return {
        "ok": True, "id": sid, "feasible": cert["feasible"],
        "reason": cert["reason"], "energy": cert["total_energy"],
        "drones_used": cert["drones_used"], "wall_time": res.wall_time,
        "budget": SOLVE_BUDGET, "replay_url": f"/results/{sid}/flight.html",
    }


def handle_dashboard(state: PlannerState, sid: str, budget_name: str) -> Dict[str, Any]:
    sess = state.sessions.get(sid)
    if sess is None:
        raise PlannerError(404, "unknown session -- solve first")
    budget = DASH_BUDGETS.get(budget_name, DASH_BUDGETS["quick"])
    inst = sess.instance

    if not state.lock.acquire(blocking=False):
        raise PlannerError(409, "a solve is already running -- wait for it "
                               "to finish")
    try:
        from drp.meta.alns import solve_alns
        from drp.meta.construct import best_construction
        from drp.meta.ga import solve_ga
        from drp.meta.sa import solve_sa
        from drp.viz.dashdata import MethodRun

        ws = best_construction(inst)
        wt = ws.giant_tour() if ws else None
        common = dict(seed=1, time_limit=budget, trace=True,
                      trace_max_samples=1500)
        ga = solve_ga(inst, warm_tours=[wt] if wt else None, **common)
        sa = solve_sa(inst, warm_tour=wt, **common)
        alns = solve_alns(inst, warm_tour=wt, **common)
        runs = [
            MethodRun("ga", ga.trace, ga.best_energy, ga.time, 1,
                      solution=ga.best_solution),
            MethodRun("sa", sa.trace, sa.best_energy, sa.time, 1,
                      solution=sa.best_solution),
            MethodRun("alns", alns.trace, alns.best_energy, alns.time, 1,
                      solution=alns.best_solution),
        ]
    finally:
        state.lock.release()

    outdir = state.session_dir(sid)
    render_dashboard_html(inst, runs, outdir / "dash.html",
                          title="planner dashboard", theme=state.theme)
    return {"ok": True, "dashboard_url": f"/results/{sid}/dash.html",
            "budget": budget}


def handle_tree(state: PlannerState, sid: str, budget_name: str) -> Dict[str, Any]:
    sess = state.sessions.get(sid)
    if sess is None:
        raise PlannerError(404, "unknown session -- solve first")
    budget = TREE_BUDGETS.get(budget_name, TREE_BUDGETS["quick"])
    inst = sess.instance

    if not state.lock.acquire(blocking=False):
        raise PlannerError(409, "a solve is already running -- wait for it "
                               "to finish")
    try:
        from drp.exact.bnb import solve_bnb
        from drp.meta.construct import best_construction

        ws = best_construction(inst)
        res = solve_bnb(inst, time_limit=budget, warm_start=ws, trace=True,
                        trace_max_nodes=TREE_MAX_NODES)
    finally:
        state.lock.release()

    outdir = state.session_dir(sid)
    render_tree_html(inst, res, outdir / "tree.html", title="planner tree",
                     theme=state.theme)
    return {"ok": True, "tree_url": f"/results/{sid}/tree.html",
            "budget": budget, "nodes_explored": res.nodes_explored,
            "optimal": res.optimal, "n_customers": inst.n_customers,
            "complete": inst.n_customers <= TREE_COMPLETE_CEILING}


# ---------------------------------------------------------------------------
# HTTP plumbing
# ---------------------------------------------------------------------------
class PlannerHandler(BaseHTTPRequestHandler):
    server: "PlannerHTTPServer"

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: D401
        pass  # every other `drp` command is quiet unless asked to print

    def _json(self, status: int, obj: Dict[str, Any]) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, status: int, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_result_file(self, sid: str, name: str) -> None:
        state = self.server.state
        root = (state.output_root / sid).resolve()
        target = (root / name).resolve()
        # Never serve outside this server's own output directory, however
        # `sid`/`name` were spelled.
        if root.parent != state.output_root.resolve() or not str(target).startswith(str(root)):
            self._json(404, {"error": "not found"})
            return
        try:
            target.relative_to(root)
        except ValueError:
            self._json(404, {"error": "not found"})
            return
        if not target.is_file():
            self._json(404, {"error": "not found"})
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        state = self.server.state
        parts = urlsplit(self.path)
        path = parts.path
        qs = parse_qs(parts.query)
        try:
            if path in ("/", "/index.html"):
                self._html(200, state.page())
            elif path.startswith("/results/"):
                rest = path[len("/results/"):]
                sid, _, name = rest.partition("/")
                if not sid or not name:
                    self._json(404, {"error": "not found"})
                else:
                    self._serve_result_file(sid, name)
            elif path == "/api/dashboard":
                sid = (qs.get("id") or [""])[0]
                budget = (qs.get("budget") or ["quick"])[0]
                self._json(200, handle_dashboard(state, sid, budget))
            elif path == "/api/tree":
                sid = (qs.get("id") or [""])[0]
                budget = (qs.get("budget") or ["quick"])[0]
                self._json(200, handle_tree(state, sid, budget))
            else:
                self._json(404, {"error": "not found"})
        except PlannerError as exc:
            self._json(exc.status, {"error": exc.message})
        except Exception as exc:  # pragma: no cover - defensive
            self._json(500, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        state = self.server.state
        parts = urlsplit(self.path)
        try:
            if parts.path != "/api/solve":
                self._json(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0:
                raise PlannerError(400, "empty request body")
            if length > MAX_BODY_BYTES:
                raise PlannerError(413, "request body too large")
            body = self.rfile.read(length)
            self._json(200, handle_solve(state, body))
        except PlannerError as exc:
            self._json(exc.status, {"error": exc.message})
        except Exception as exc:  # pragma: no cover - defensive
            self._json(500, {"error": str(exc)})


class PlannerHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, state: PlannerState):
        super().__init__(address, handler)
        self.state = state


def make_server(host: str = "127.0.0.1", port: int = 0,
                theme: Optional[str] = None,
                output_root: Optional[Path] = None) -> PlannerHTTPServer:
    """Build (but do not start) a planner server.

    A factory rather than only a CLI path, so tests and the browser-test
    harness can start and stop one directly -- no argparse, no real browser
    window. `host` should stay loopback: this server runs whatever solver a
    request asks for, with no authentication, which is fine on `127.0.0.1`
    and is not something to expose on a network.
    """
    root = Path(output_root) if output_root else Path(tempfile.mkdtemp(prefix="drp-serve-"))
    root.mkdir(parents=True, exist_ok=True)
    state = PlannerState(root, theme=theme)
    return PlannerHTTPServer((host, port), PlannerHandler, state)
