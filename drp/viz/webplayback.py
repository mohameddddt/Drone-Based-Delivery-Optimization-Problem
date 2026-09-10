"""Render the GSAP flight-playback page (roadmap §2.2) to a single HTML file.

The template (`drp/viz/web/playback_template.html`) is a complete, self-contained
document -- open it directly in a browser, nothing to serve. This module's only
job is to fill in the placeholders: the instance name (for the `<title>`, so the
file is identifiable from a browser tab), the JSON payload from
`drp.viz.webdata.build_playback_data`, and -- optionally -- a Solver Vision
payload from `drp.viz.treedata.build_vision_data` (roadmap §2.4, step 4).

Solver Vision is `null` unless a caller passes one, and the page draws nothing
in its place when it is: the candidate routes it shows are the ones a real,
traced B&B search considered and rejected, or there are none.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Optional, Union

from typing import Any, Dict

from drp.core.instance import DRPInstance
from drp.core.solution import Solution
from drp.viz.webdata import build_playback_data

PathLike = Union[str, Path]

TEMPLATE_PATH = Path(__file__).parent / "web" / "playback_template.html"
DATA_TOKEN = "__DRP_PLAYBACK_DATA_JSON__"
NAME_TOKEN = "__DRP_INSTANCE_NAME__"
VISION_TOKEN = "__DRP_VISION_DATA_JSON__"


def render_playback_html(inst: DRPInstance,
                         sol: Solution,
                         path: PathLike = "playback.html",
                         title: Optional[str] = None,
                         separation: Optional[float] = None,
                         vision: Optional[Dict[str, Any]] = None) -> Path:
    """Write the interactive flight-playback page for `sol` to `path`.

    `vision` is an optional `drp.viz.treedata.build_vision_data` payload; pass
    one to turn on Solver Vision, which draws the partial routes a traced B&B
    search considered and rejected at each point along a drone's route.
    """
    data = build_playback_data(inst, sol, separation=separation, title=title)
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    # `</` would otherwise let a string field (e.g. an imported instance name)
    # break out of the enclosing <script> tag.
    payload = json.dumps(data).replace("</", "<\\/")
    vis = json.dumps(vision).replace("</", "<\\/") if vision else "null"
    page = (template
            .replace(NAME_TOKEN, html.escape(inst.name))
            .replace(VISION_TOKEN, vis)
            .replace(DATA_TOKEN, payload))

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out
