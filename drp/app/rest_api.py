from __future__ import annotations

import json
import math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

from drp.eval.runner import METHODS, solve_one
from drp.instances.io import instance_from_dict, solution_to_dict

MAX_BODY_BYTES = 2_000_000
MAX_TIME_LIMIT = 60.0


class APIError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _request_from_body(body: bytes) -> tuple[Any, str, int, float]:
    try:
        request = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise APIError(400, f"malformed JSON: {exc}") from None
    if not isinstance(request, dict):
        raise APIError(400, "request body must be a JSON object")
    method = request.get("method")
    if not isinstance(method, str) or method.lower() not in METHODS:
        raise APIError(400, f"method must be one of {', '.join(METHODS)}")
    seed = request.get("seed", 1)
    if not isinstance(seed, int):
        raise APIError(400, "seed must be an integer")
    time_limit = request.get("time_limit", 5.0)
    if (not isinstance(time_limit, (int, float)) or isinstance(time_limit, bool)
            or not 0 < time_limit <= MAX_TIME_LIMIT):
        raise APIError(400, f"time_limit must be between 0 and {MAX_TIME_LIMIT:g} seconds")
    try:
        instance = instance_from_dict(request["instance"])
    except (KeyError, TypeError, ValueError) as exc:
        raise APIError(400, f"malformed drp-instance/v1: {exc}") from None
    return instance, method.lower(), seed, float(time_limit)


def handle_solve(body: bytes) -> dict[str, Any]:
    instance, method, seed, time_limit = _request_from_body(body)
    result = solve_one(instance, method, seed=seed, time_limit=time_limit)
    solution = (solution_to_dict(instance, result.solution, method=result.method,
                                 meta={"wall_time": result.wall_time,
                                       "dual_bound": result.dual_bound,
                                       "optimal": result.optimal})
                if result.solution is not None else None)
    certificate = solution["certificate"] if solution is not None else None
    return {"ok": True, "method": result.method, "feasible": result.feasible,
            "energy": None if math.isinf(result.energy) else result.energy,
            "wall_time": result.wall_time, "dual_bound": result.dual_bound,
            "optimal": result.optimal, "nodes": result.nodes,
            "iterations": result.iterations, "solution": solution,
            "certificate": certificate}


class RESTHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: D401
        pass

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/solve":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            self._json(400, {"error": "empty request body"})
            return
        if length > MAX_BODY_BYTES:
            self._json(413, {"error": "request body too large"})
            return
        try:
            self._json(200, handle_solve(self.rfile.read(length)))
        except APIError as exc:
            self._json(exc.status, {"error": exc.message})


def make_api_server(host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), RESTHandler)
