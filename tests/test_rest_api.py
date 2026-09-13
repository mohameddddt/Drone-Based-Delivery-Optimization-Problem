from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Any

import pytest

from drp.app.rest_api import make_api_server


def _instance() -> dict[str, Any]:
    return {
        "schema": "drp-instance/v1",
        "name": "api-fixture",
        "fleet": {"n_drones": 2, "payload": 20.0, "battery": 450.0},
        "energy": {"alpha": 1.0, "beta": 0.3},
        "geodesic": False,
        "round_distances": False,
        "depot": [50.0, 50.0],
        "customers": [
            {"id": 1, "coord": [30.0, 30.0], "demand": 2.0},
            {"id": 2, "coord": [70.0, 70.0], "demand": 2.0},
        ],
        "nofly": {"edges": [], "polygons": []},
        "seed": 1,
    }


@pytest.fixture
def api_server():
    srv = make_api_server()
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    host, port = srv.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        srv.shutdown()
        thread.join(timeout=5)
        srv.server_close()


def _post(base: str, body: bytes) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(base + "/v1/solve", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_synchronous_solve_returns_the_existing_solution_and_certificate(api_server):
    request = {"instance": _instance(), "method": "greedy", "time_limit": 1.0}
    status, response = _post(api_server, json.dumps(request).encode("utf-8"))
    assert status == 200
    assert response["ok"] is True
    assert response["method"] == "greedy"
    assert response["solution"]["schema"] == "drp-solution/v1"
    assert response["certificate"]["feasible"] is True
    assert response["certificate"] == response["solution"]["certificate"]


def test_unknown_method_is_a_client_error(api_server):
    request = {"instance": _instance(), "method": "unknown", "time_limit": 1.0}
    status, response = _post(api_server, json.dumps(request).encode("utf-8"))
    assert status == 400
    assert "method" in response["error"]
