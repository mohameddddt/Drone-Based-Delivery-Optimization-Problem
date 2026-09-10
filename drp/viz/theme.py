"""One theme for every view (roadmap 2.5).

There are two of them and they are interchangeable:

``chart``
    The original aeronautical-chart identity, every hex unchanged, so a figure
    that was drawn with it can be drawn with it again. Note what that does and
    does not promise: it restores the *palette*, not a pre-2.5 figure. Roadmap
    2.5 also resized figure type for where the figure lands on the page, and
    that applies to both themes -- `tests/test_viz_theme.py` pins the colours,
    not the bytes.

``safe``
    The default. Built for dichromatic vision and *measured* for it -- see
    `drp/viz/cvd.py` and `tests/test_viz_theme.py`, which simulate protanopia,
    deuteranopia and tritanopia over every colour this module names and assert
    the separations below.

Why ``chart`` had to be replaced rather than tweaked, in numbers. Its six route
colours are ``#2E75B6 #C0504D #4E8542 #8064A2 #F79646 #4BACC6``. Simulated, the
closest pair in that set falls to dE*ab 26.2 for normal vision, 9.4 under
protanopia (blue / purple), **7.8 under deuteranopia (red / green)** and 16.4
under tritanopia. A dE of 7.8 is "the same colour with a bad print". ``safe``
scores 29.5 at its worst pair across all three deficiencies -- and its route
palette is also held clear of the *semantic* colours, so no hex ever means two
things at once.

That last separation is 11.2 at its tightest, which is not a lot, and it is a
deliberate limit rather than an oversight: six route colours, five semantic
ones and a sequential ramp cannot all be mutually far apart at 3:1 contrast on
a cream page. The pairs that end up closest -- a dark red route against the
crimson a breach flashes in -- are drawn as different *kinds* of mark, a stroke
against a dashed ring with a labelled banner. Which is the reason colour is
never allowed to be the only channel.

The ramp was the surprise. The tree explorer's teal -> amber -> magenta bound
ramp was expected to be close to safe. It is not: under deuteranopia its far end
lands dE 9.3 from its near end while its **middle** is 58.3 away, so the ramp
folds back on itself and the highest bounds look like the lowest -- and it is
not monotone for normal vision either. ``safe``'s ramp is monotone in perceived
distance under all four, which is the property a sequential ramp actually
needs.

**Colour is never the only channel.** Every theme also carries dash patterns,
marker shapes and bar hatches, keyed the same way as the colours, so a route, a
method or a node status is identifiable in greyscale and to a monochromat --
whom no palette can help.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

#: Environment variable read on first use; ``--theme`` overrides it.
ENV_VAR = "DRP_VIZ_THEME"


@dataclass(frozen=True)
class Theme:
    """Everything any view needs to draw itself, in one object.

    `palette`, `dashes`, `markers` and `hatches` are parallel cycles: index `i`
    is drone `i`'s colour *and* its dash pattern *and* its marker. Views index
    them together, so the identity survives a greyscale print.
    """

    name: str
    label: str
    description: str

    # --- categorical: one entry per drone / route ---------------------------
    palette: Tuple[str, ...]
    #: SVG ``stroke-dasharray`` values. ``""`` is solid.
    dashes: Tuple[str, ...]
    #: matplotlib marker codes.
    markers: Tuple[str, ...]
    #: matplotlib bar hatches.
    hatches: Tuple[str, ...]

    # --- semantic -----------------------------------------------------------
    ink: str
    muted: str
    muted2: str
    line: str
    line2: str
    paper: str
    paper2: str
    panel: str
    accent: str
    accent2: str
    restricted: str
    caution: str
    warn: str
    success: str
    water: str

    #: Sequential ramp for the tree explorer's lower bound, low -> high.
    ramp: Tuple[str, ...]

    #: Per-method colours, and the matching second channels.
    method_colors: Dict[str, str] = field(default_factory=dict)
    method_dashes: Dict[str, str] = field(default_factory=dict)
    method_markers: Dict[str, str] = field(default_factory=dict)

    #: Per-status dash patterns for the tree explorer's node rings.
    status_dashes: Dict[str, str] = field(default_factory=dict)

    # --- accessors ----------------------------------------------------------
    def color(self, i: int) -> str:
        return self.palette[i % len(self.palette)]

    def dash(self, i: int) -> str:
        return self.dashes[i % len(self.dashes)]

    def marker(self, i: int) -> str:
        return self.markers[i % len(self.markers)]

    def hatch(self, i: int) -> str:
        return self.hatches[i % len(self.hatches)]

    def mpl_dash(self, i: int):
        """``dashes[i]`` as a matplotlib linestyle."""
        return _svg_dash_to_mpl(self.dash(i))

    def method_color(self, m: str, fallback: int = 0) -> str:
        return self.method_colors.get(m, self.color(fallback))

    def method_dash(self, m: str) -> str:
        return self.method_dashes.get(m, "")

    def method_mpl_dash(self, m: str):
        return _svg_dash_to_mpl(self.method_dash(m))

    def method_marker(self, m: str) -> str:
        return self.method_markers.get(m, "o")

    def to_dict(self) -> Dict[str, Any]:
        """The half a browser page needs, for inlining into a payload.

        Kept flat and JSON-only on purpose: the pages read it straight out of
        ``DATA.theme`` and write it into CSS custom properties, so adding a key
        here is all it takes to make a new colour themeable.
        """
        return {
            "name": self.name,
            "label": self.label,
            "palette": list(self.palette),
            "dashes": list(self.dashes),
            "ramp": list(self.ramp),
            "method_colors": dict(self.method_colors),
            "method_dashes": dict(self.method_dashes),
            "status_dashes": dict(self.status_dashes),
            "tokens": {
                "ink": self.ink, "muted": self.muted, "muted2": self.muted2,
                "line": self.line, "line2": self.line2, "paper": self.paper,
                "paper2": self.paper2, "panel": self.panel,
                "accent": self.accent, "accent2": self.accent2,
                "restricted": self.restricted, "caution": self.caution,
                "warn": self.warn, "success": self.success, "water": self.water,
            },
        }


def _svg_dash_to_mpl(d: str):
    """``"7 3"`` -> ``(0, (7, 3))``; ``""`` -> ``"solid"``."""
    if not d:
        return "solid"
    return (0, tuple(float(v) for v in d.replace(",", " ").split()))


# Shared across both themes: the second channel does not need to change when
# the colours do, and keeping it identical means a figure's *shapes* stay
# comparable between the two.
_DASHES = ("", "7 3", "2 3", "10 3 2 3", "4 2 1 2", "1 3")
_MARKERS = ("o", "s", "^", "D", "v", "P")
_HATCHES = ("", "///", "...", "xx", "\\\\\\", "++")
_METHOD_DASHES = {"greedy": "1 3", "bnb": "", "ga": "7 3", "sa": "2 3",
                  "alns": "10 3 2 3"}
_METHOD_MARKERS = {"greedy": "v", "bnb": "o", "ga": "s", "sa": "^", "alns": "D"}
_STATUS_DASHES = {"pruned_bound": "", "new_incumbent": "3 2",
                  "infeasible": "1 2", "dominated": "1 2", "timeout": "5 2"}


CHART = Theme(
    name="chart",
    label="Aeronautical chart",
    description=("The original palette. Adjacent red and green: its worst pair "
                 "falls to dE 7.8 under deuteranopia. Kept so a figure drawn "
                 "with it can be drawn with it again."),
    palette=("#2E75B6", "#C0504D", "#4E8542", "#8064A2", "#F79646", "#4BACC6"),
    dashes=_DASHES, markers=_MARKERS, hatches=_HATCHES,
    ink="#1B1F1A", muted="#585D51", muted2="#8A8F80",
    line="#D3D5C8", line2="#BFC2B3",
    paper="#EDEBE1", paper2="#E2DFD2", panel="#FBFAF5",
    accent="#2C4F55", accent2="#3E7078",
    restricted="#8E2F63", caution="#B23A22", warn="#9C6B12", success="#3E7A3C",
    water="#BCD3D8",
    # The original three-stop ramp: teal -> amber -> magenta.
    ramp=("#3A8674", "#B08830", "#8E2F63"),
    method_colors={"greedy": "#808080", "bnb": "#4E8542", "ga": "#2E75B6",
                   "sa": "#C0504D", "alns": "#8064A2"},
    method_dashes=dict(_METHOD_DASHES), method_markers=dict(_METHOD_MARKERS),
    status_dashes=dict(_STATUS_DASHES),
)

SAFE = Theme(
    name="safe",
    label="Colour-blind safe",
    description=("Route colours optimised for worst-pair separation under "
                 "simulated protanopia, deuteranopia and tritanopia, at >=3:1 "
                 "contrast on the page background, and held clear of the "
                 "semantic colours so no hex carries two meanings."),
    palette=("#002E89", "#B60012", "#52245B", "#7680BF", "#6D0924", "#AD7689"),
    dashes=_DASHES, markers=_MARKERS, hatches=_HATCHES,
    ink="#1A1D22", muted="#545963", muted2="#868C96",
    line="#D2D4CE", line2="#BDC0B9",
    paper="#EDEBE1", paper2="#E2DFD2", panel="#FBFAF5",
    accent="#155E52", accent2="#1E7A69",
    restricted="#7A2E86", caution="#971820", warn="#CA6A00", success="#0080DF",
    water="#BCD3D8",
    # Monotone in perceived distance under all three deficiencies: navy ->
    # violet -> amber. The chart theme's teal -> amber -> magenta folds back.
    ramp=("#1B3A7A", "#7A5A9E", "#C77A3B"),
    # Methods reuse the route palette, because the two never appear in one
    # figure -- a routes plot has no methods, a comparison plot has no routes.
    # The four chosen are the four with the strongest contrast against the
    # near-white panel the dashboard draws its curves on, which rules out the
    # two pale entries; a thin line needs more contrast than a filled swatch.
    # Worst pair across all three deficiencies: dE 29.5.
    method_colors={"greedy": "#7E838B", "bnb": "#002E89", "ga": "#B60012",
                   "sa": "#52245B", "alns": "#6D0924"},
    method_dashes=dict(_METHOD_DASHES), method_markers=dict(_METHOD_MARKERS),
    status_dashes=dict(_STATUS_DASHES),
)

THEMES: Dict[str, Theme] = {t.name: t for t in (SAFE, CHART)}
DEFAULT_THEME = "safe"

_active: Optional[Theme] = None


def get_theme(name: Optional[str] = None) -> Theme:
    """Look one up by name without changing the active theme."""
    if name is None:
        return active_theme()
    key = str(name).strip().lower()
    if key not in THEMES:
        raise ValueError(f"unknown theme {name!r}; expected one of "
                         f"{sorted(THEMES)}")
    return THEMES[key]


def active_theme() -> Theme:
    """The theme every view draws with unless handed another explicitly."""
    global _active
    if _active is None:
        env = os.environ.get(ENV_VAR, "").strip().lower()
        _active = THEMES.get(env, THEMES[DEFAULT_THEME])
    return _active


def use_theme(name) -> Theme:
    """Set the active theme. Accepts a name or a `Theme`."""
    global _active
    _active = name if isinstance(name, Theme) else get_theme(name)
    return _active


def theme_names() -> List[str]:
    return list(THEMES)


def resolve(theme=None) -> Theme:
    """`None` -> the active theme; a name or a `Theme` -> that one.

    Every drawing entry point takes an optional ``theme=`` and passes it through
    here, so a caller can render two themes side by side in one process without
    touching global state -- which is how the before/after comparison in
    `docs/VISUALISATION.md` is produced.
    """
    if theme is None:
        return active_theme()
    if isinstance(theme, Theme):
        return theme
    return get_theme(theme)
