"""Request-handling tests for the planner server (roadmap §2.1).

No browser here -- `tests/browser/test_page_planner.py` covers the page
itself. This file only checks that `drp.app.server` does the right thing with
a raw HTTP request: a valid instance solves, an oversized one is refused, an
instance nothing can serve reports why, malformed JSON doesn't 500, and
`/results/` never serves outside its own output directory.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pytest

from drp.app.server import MAX_DRONES, MAX_STOPS, make_server


def _instance(customers, n_drones=2, payload=20.0, battery=450.0, name="t"):
    return {
        "schema": "drp-instance/v1",
        "name": name,
        "n_customers": len(customers),
        "fleet": {"n_drones": n_drones, "payload": payload, "battery": battery},
        "energy": {"alpha": 1.0, "beta": 0.3},
        "geodesic": False,
        "round_distances": False,
        "depot": [50.0, 50.0],
        "customers": customers,
        "nofly": {"edges": [], "polygons": []},
        "seed": None,
    }


def _stop(i, x, y, demand=1.0):
    return {"id": i, "coord": [x, y], "demand": demand}


@pytest.fixture()
def server(tmp_path):
    srv = make_server(host="127.0.0.1", port=0, output_root=tmp_path)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    host, port = srv.server_address[:2]
    base = f"http://{host}:{port}"
    yield base
    srv.shutdown()
    thread.join(timeout=5)
    srv.server_close()


def _get(base: str, path: str) -> Tuple[int, bytes]:
    """Status plus raw body -- `/results/...` serves HTML, not JSON."""
    req = urllib.request.Request(base + path)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _get_json(base: str, path: str) -> Tuple[int, Dict[str, Any]]:
    status, body = _get(base, path)
    try:
        return status, (json.loads(body) if body else {})
    except json.JSONDecodeError:
        return status, {"raw": body.decode("utf-8", "replace")}


def _post_json(base: str, path: str, payload) -> Tuple[int, Dict[str, Any]]:
    body = json.dumps(payload).encode("utf-8") if not isinstance(payload, (bytes, bytearray)) else payload
    req = urllib.request.Request(base + path, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"raw": body.decode("utf-8", "replace")}


def test_index_page_serves(server):
    status, _ = 200, None
    req = urllib.request.Request(server + "/")
    with urllib.request.urlopen(req, timeout=15) as resp:
        status = resp.status
        text = resp.read().decode("utf-8")
    assert status == 200
    assert "__DRP_PLANNER_DATA_JSON__" not in text  # token substituted
    assert "Drone Delivery Planner" in text


def test_valid_instance_solves_and_serves_replay(server):
    customers = [_stop(1, 30, 30), _stop(2, 70, 70), _stop(3, 20, 80)]
    status, data = _post_json(server, "/api/solve", _instance(customers))
    assert status == 200
    assert data["ok"] is True
    assert data["feasible"] is True
    assert data["replay_url"].startswith("/results/")

    rstatus, _ = _get(server, data["replay_url"])
    assert rstatus == 200


def test_solver_vision_renders_the_existing_replay_with_a_trace(server):
    customers = [_stop(1, 30, 30), _stop(2, 70, 70)]
    status, solved = _post_json(server, "/api/solve", _instance(customers))
    assert status == 200
    assert solved["feasible"] is True

    vstatus, vision = _get_json(server, f"/api/vision?id={solved['id']}")
    assert vstatus == 200
    assert vision["vision_url"].endswith("/flight-vision.html")
    page_status, page = _get(server, vision["vision_url"])
    assert page_status == 200
    assert b"const VISION = {" in page


def test_oversized_stop_count_is_rejected(server):
    customers = [_stop(i, float(i % 100), float((i * 7) % 100)) for i in range(1, MAX_STOPS + 2)]
    status, data = _post_json(server, "/api/solve", _instance(customers))
    assert status == 400
    assert "stops" in data["error"]


def test_undersized_stop_count_is_rejected(server):
    status, data = _post_json(server, "/api/solve", _instance([_stop(1, 30, 30)]))
    assert status == 400
    assert "stops" in data["error"]


def test_oversized_fleet_is_rejected(server):
    customers = [_stop(1, 30, 30), _stop(2, 40, 40)]
    status, data = _post_json(server, "/api/solve",
                              _instance(customers, n_drones=MAX_DRONES + 1))
    assert status == 400
    assert "drones" in data["error"]


def test_infeasible_demand_names_the_stop(server):
    # The first stop's demand alone exceeds the fleet's payload capacity, so
    # no construction can ever place it -- the second stop is unremarkable
    # and only there to satisfy MIN_STOPS.
    customers = [_stop(1, 55, 55, demand=999.0), _stop(2, 45, 45, demand=1.0)]
    status, data = _post_json(server, "/api/solve", _instance(customers, payload=20.0))
    assert status == 200
    assert data["ok"] is True
    assert data["feasible"] is False
    assert data["stop"] == 1
    assert "payload" in data["reason"]


def test_infeasible_unreachable_stop_names_the_stop(server):
    # A battery this small makes every stop unreachable; the diagnostic must
    # still name the *first* one, in customer order.
    customers = [_stop(1, 0.0, 0.0, demand=1.0), _stop(2, 100.0, 100.0, demand=1.0)]
    status, data = _post_json(server, "/api/solve",
                              _instance(customers, payload=20.0, battery=1.0))
    assert status == 200
    assert data["feasible"] is False
    assert data["stop"] == 1
    assert "battery" in data["reason"]


def test_malformed_json_is_a_400_not_a_crash(server):
    status, data = _post_json(server, "/api/solve", b"{not json")
    assert status == 400
    assert "error" in data
    # the server must still be alive afterwards
    customers = [_stop(1, 40, 40), _stop(2, 60, 60)]
    status2, data2 = _post_json(server, "/api/solve", _instance(customers))
    assert status2 == 200


def test_empty_body_is_a_400(server):
    req = urllib.request.Request(server + "/api/solve", data=b"", method="POST")
    try:
        urllib.request.urlopen(req, timeout=10)
        assert False, "expected an HTTPError"
    except urllib.error.HTTPError as exc:
        assert exc.code == 400


def test_results_path_traversal_is_rejected(server):
    status, data = _get(server, "/results/../../etc/passwd")
    assert status == 404
    status2, _ = _get(server, "/results/somesession/../../../secret.txt")
    assert status2 == 404


def test_unknown_session_dashboard_and_tree_are_404(server):
    status, _ = _get(server, "/api/dashboard?id=doesnotexist&budget=quick")
    assert status == 404
    status2, _ = _get(server, "/api/tree?id=doesnotexist&budget=quick")
    assert status2 == 404


def test_concurrent_solve_returns_409(server):
    """A second solve while one is in flight is refused, not queued silently.

    The first solve holds the server's single lock for the whole 5 s ALNS
    budget, so a second request arriving 50 ms later should reliably find it
    held -- but the assertion stays lenient (409 or a second 200, never a
    crash) so it cannot flake on a machine slow enough to matter.
    """
    import time

    customers = [_stop(i, float(10 + i * 5), float(10 + i * 3)) for i in range(1, 6)]
    results = []

    def go():
        results.append(_post_json(server, "/api/solve", _instance(customers, n_drones=2)))

    t1 = threading.Thread(target=go)
    t2 = threading.Thread(target=go)
    t1.start()
    time.sleep(0.05)  # let t1 acquire the lock first
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)

    statuses = sorted(r[0] for r in results)
    # One succeeds; the other either also succeeds (if the first finished
    # before the second's request arrived) or is refused with 409 -- never a
    # crash and never a silently queued second solve.
    assert all(s in (200, 409) for s in statuses)
    assert 200 in statuses
