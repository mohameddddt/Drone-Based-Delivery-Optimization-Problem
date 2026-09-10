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
from typing import Any, Dict, Optional, Union

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
                         separation: Optional[float] = None,
                         basemap: Optional[Union[Dict[str, Any], PathLike]] = None
                         ) -> Path:
    """Write the interactive flight-playback page for `sol` to `path`.

    `basemap` may be a ``drp-basemap/v1`` mapping, a path to one, or a path to
    an ``.osm`` extract to build one from (roadmap §3.4). With it the page draws
    real streets and water instead of the chart it invents; the geometry is
    embedded in the file, so the page stays self-contained and works offline.
    """
    if basemap is not None and not isinstance(basemap, dict):
        basemap = _basemap_from(basemap, inst)
    data = build_playback_data(inst, sol, separation=separation, title=title,
                               basemap=basemap)
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


def _basemap_from(source: Any, inst: DRPInstance) -> Dict[str, Any]:
    """A prebuilt basemap JSON, a parsed extract, or a path to either."""
    from drp.geometry.osm import OSMData
    from drp.viz.basemap import basemap_for_instance, load_basemap

    if isinstance(source, OSMData):
        return basemap_for_instance(inst, source)
    p = Path(source)
    if p.suffix.lower() == ".json":
        return load_basemap(p)
    return basemap_for_instance(inst, p)
