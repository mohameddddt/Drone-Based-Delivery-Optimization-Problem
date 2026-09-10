"""Render the metaheuristic convergence dashboard (roadmap §2.4) to one file.

Exactly the shape of `drp.viz.webplayback` and `drp.viz.webtree`: the template
(`drp/viz/web/dashboard_template.html`) is a complete self-contained document --
open it directly in a browser, nothing to serve -- and this module's only job is
to substitute the instance name and the JSON payload from
`drp.viz.dashdata.build_dashboard_data`.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Optional, Sequence, Union

from drp.core.instance import DRPInstance
from drp.viz.dashdata import MethodRun, build_dashboard_data

PathLike = Union[str, Path]

TEMPLATE_PATH = Path(__file__).parent / "web" / "dashboard_template.html"
DATA_TOKEN = "__DRP_DASH_DATA_JSON__"
NAME_TOKEN = "__DRP_INSTANCE_NAME__"


def render_dashboard_html(inst: DRPInstance,
                          runs: Sequence[MethodRun],
                          path: PathLike = "dashboard.html",
                          reference: Optional[float] = None,
                          reference_label: str = "",
                          title: Optional[str] = None,
                          theme=None) -> Path:
    """Write the convergence dashboard for `runs` to `path`.

    Each run must carry a trace (the solver called with ``trace=True``).
    `theme` is a name or a `drp.viz.theme.Theme`.
    """
    data = build_dashboard_data(inst, runs, reference=reference,
                                reference_label=reference_label, title=title,
                                theme=theme)
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
