"""Render the B&B tree explorer (roadmap §2.4) to a single HTML file.

Exactly the shape of `drp.viz.webplayback`: the template
(`drp/viz/web/tree_template.html`) is a complete self-contained document -- open
it directly in a browser, nothing to serve -- and this module's only job is to
substitute the instance name and the JSON payload from
`drp.viz.treedata.build_tree_data`.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Optional, Union

from drp.core.instance import DRPInstance
from drp.exact.bnb import BnBResult
from drp.viz.treedata import build_tree_data

PathLike = Union[str, Path]

TEMPLATE_PATH = Path(__file__).parent / "web" / "tree_template.html"
DATA_TOKEN = "__DRP_TREE_DATA_JSON__"
NAME_TOKEN = "__DRP_INSTANCE_NAME__"


def render_tree_html(inst: DRPInstance,
                     res: BnBResult,
                     path: PathLike = "tree.html",
                     title: Optional[str] = None) -> Path:
    """Write the B&B tree explorer for `res` to `path`.

    `res` must carry a trace (``solve_bnb(..., trace=True)``).
    """
    data = build_tree_data(inst, res, title=title)
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
