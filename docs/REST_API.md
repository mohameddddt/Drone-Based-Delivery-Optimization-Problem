# REST API

This is the deliberately small first slice of roadmap §7-8: one loopback-only
endpoint for solving the same `drp-instance/v1` document accepted by the CLI.
It is not the interactive planner server, has no browser pages, and does not
create a persistent job store.

Start it from the repository root:

```bash
drp api
```

It listens on `http://127.0.0.1:8000` by default. Use `--port` to choose a
different port. Keep the default host: this first slice has no authentication
or tenancy and must not be exposed on a network.

## `POST /v1/solve`

The body contains an instance in the existing JSON schema and the method to
run. `method` is one of `greedy`, `bnb`, `ga`, `sa`, or `alns`; `seed` defaults
to `1`; `time_limit` defaults to `5.0` seconds and is capped at 60 seconds.

```json
{
  "instance": {"schema": "drp-instance/v1", "...": "the normal instance fields"},
  "method": "alns",
  "seed": 1,
  "time_limit": 5.0
}
```

The response is synchronous. It returns when `drp.eval.runner.solve_one` has
returned, so the caller chooses a bounded wait through `time_limit`. A feasible
response carries the existing `drp-solution/v1` representation and repeats its
feasibility certificate at top level for clients that only need the verdict:

```json
{
  "ok": true,
  "method": "alns",
  "feasible": true,
  "energy": 922.1,
  "wall_time": 5.0,
  "dual_bound": null,
  "optimal": false,
  "nodes": null,
  "iterations": 1234,
  "solution": {"schema": "drp-solution/v1", "certificate": {"feasible": true}},
  "certificate": {"feasible": true}
}
```

Malformed JSON, an invalid `drp-instance/v1` body, an unknown method, or an
out-of-range time limit returns `400` with `{"error": "..."}`. A request may
be up to 2 MB.

## Why synchronous stdlib HTTP for now

Synchronous response is intentional here. The methods are bounded by the
request's time limit, and a submit/poll design would need durable job IDs,
status retention, cancellation semantics, and eviction policy before it made
the single endpoint more useful. This endpoint is a local integration seam,
not yet a multi-user service.

`http.server` remains the right dependency choice for the same reason: the
planner already proves that a small local loopback server can serve this
project without a framework. FastAPI or Flask would add a public framework
contract and deployment machinery before this API has authentication, a job
model, or more than one route. Revisit that decision when submit/poll, OpenAPI,
or non-local deployment becomes a real requirement.

Docker, a delivery simulator, and a documentation site are expressly outside
this slice and remain the work left in §7-8.
