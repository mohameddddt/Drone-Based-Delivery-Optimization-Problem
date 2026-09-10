"""Render the GSAP flight-playback page (roadmap §2.2) to a single HTML file.

The template (`drp/viz/web/playback_template.html`) is a complete, self-contained
document -- open it directly in a browser, nothing to serve. This module's only
job is to fill in the two placeholders: the instance name (for the `<title>`,
so the file is identifiable from a browser tab) and the JSON payload from
`drp.viz.webdata.build_playback_data`.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Optional, Union

from drp.core.instance import DRPInstance
from drp.core.solution import Solution
from drp.viz.webdata import build_playback_data

PathLike = Union[str, Path]

TEMPLATE_PATH = Path(__file__).parent / "web" / "playback_template.html"
DATA_TOKEN = "__DRP_PLAYBACK_DATA_JSON__"
NAME_TOKEN = "__DRP_INSTANCE_NAME__"


def render_playback_html(inst: DRPInstance,
                         sol: Solution,
                         path: PathLike = "playback.html",
                         title: Optional[str] = None,
                         separation: Optional[float] = None) -> Path:
    """Write the interactive flight-playback page for `sol` to `path`."""
    data = build_playback_data(inst, sol, separation=separation, title=title)
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    # `</` would otherwise let a string field (e.g. an imported instance name)
    # break out of the enclosing <script> tag.
    payload = json.dumps(data).replace("</", "<\\/")
    page = (template
            .replace(NAME_TOKEN, html.escape(inst.name))
            .replace(DATA_TOKEN, payload))

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out
