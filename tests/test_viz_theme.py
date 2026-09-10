"""The colour-blind-safe theme, and the simulation that justifies calling it
that (roadmap §2.5).

Two things are being tested, and they are different in kind.

`drp/viz/cvd.py` is *arithmetic*: it either implements Viénot 1999 and Brettel
1997 or it does not, and the published behaviour of those transforms on the
sRGB primaries pins it. If this half is wrong, everything below is measuring
nothing, so it is checked first and against values that do not come from this
repository.

`drp/viz/theme.py` is a *claim*: that `safe`'s colours stay apart under
dichromatic vision, that the sequential ramp does not fold back on itself, that
no colour carries two meanings, and that nothing depends on colour alone. Those
are the assertions below, with the numbers written into them, so a future
palette edit that quietly undoes one fails here rather than in someone's eyes.
"""
from __future__ import annotations

import pytest

from drp.viz import cvd
from drp.viz.theme import (CHART, DEFAULT_THEME, SAFE, THEMES, Theme,
                           active_theme, get_theme, resolve, use_theme)

DEFICIENCIES = ("protanopia", "deuteranopia", "tritanopia")

#: The page background every view draws on. Contrast is measured against this
#: rather than white because it is lighter-adjacent and it is what is actually
#: behind a route stroke.
PAPER = "#EDEBE1"
#: The panels the dashboard draws its curves on -- lighter still, so it is the
#: stricter test for a dark line.
PANEL = "#FBFAF5"


def _relative_luminance(hexcode: str) -> float:
    def f(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = cvd.hex_to_rgb(hexcode)
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast_ratio(a: str, b: str) -> float:
    la, lb = sorted((_relative_luminance(a), _relative_luminance(b)))
    return (lb + 0.05) / (la + 0.05)


# ---------------------------------------------------------------------------
# the simulation itself
# ---------------------------------------------------------------------------
def test_simulation_leaves_neutral_greys_alone():
    """A dichromat sees no colour in grey either, so the transform must be the
    identity on the neutral axis. This catches a transposed matrix, which
    otherwise produces plausible-looking nonsense."""
    for grey in ("#000000", "#404040", "#808080", "#C0C0C0", "#FFFFFF"):
        for kind in DEFICIENCIES:
            got = cvd.simulate(grey, kind)
            assert cvd.delta_e(got, grey) < 1.5, f"{grey} -> {got} under {kind}"


def test_protanopia_and_deuteranopia_confuse_red_with_green():
    """The defining property. Under both, pure red and pure green must collapse
    towards the same yellow; under tritanopia they must not."""
    for kind in ("protanopia", "deuteranopia"):
        red, green = cvd.simulate("#FF0000", kind), cvd.simulate("#00FF00", kind)
        # Both become yellows: red and green channels high, blue low.
        for c in (red, green):
            r, g, b = cvd.hex_to_rgb(c)
            assert b < 0.25, f"{c} under {kind} kept a blue component"
            assert abs(r - g) < 0.12, f"{c} under {kind} is not on the yellow axis"
    tri_red, tri_green = cvd.simulate("#FF0000", "tritanopia"), \
        cvd.simulate("#00FF00", "tritanopia")
    assert cvd.delta_e(tri_red, tri_green) > 60


def test_protanopia_leaves_blue_alone_and_tritanopia_does_not():
    """The two axes are different: protanopes and deuteranopes keep the
    blue-yellow axis, tritanopes lose it."""
    assert cvd.delta_e(cvd.simulate("#0000FF", "protanopia"), "#0000FF") < 3
    assert cvd.delta_e(cvd.simulate("#0000FF", "tritanopia"), "#0000FF") > 60


def test_simulating_normal_vision_is_the_identity():
    for c in ("#2E75B6", "#C0504D", "#4E8542"):
        assert cvd.simulate(c, "normal") == c.upper()


def test_delta_e_is_zero_for_a_colour_against_itself():
    assert cvd.delta_e("#2E75B6", "#2E75B6") == pytest.approx(0.0, abs=1e-9)


def test_unknown_deficiency_is_an_error_not_a_silent_passthrough():
    with pytest.raises(ValueError):
        cvd.simulate("#2E75B6", "tetranopia")


def test_min_separation_finds_the_actual_closest_pair():
    cols = ["#000000", "#FFFFFF", "#010101"]
    d, pair = cvd.min_separation(cols, "normal")
    assert set(pair) == {"#000000", "#010101"}
    assert d < 1.0


# ---------------------------------------------------------------------------
# what the old palette actually does -- the reason for the new one
# ---------------------------------------------------------------------------
def test_the_chart_palette_fails_deuteranopia():
    """Evidence, not a regression guard. `chart`'s red `#C0504D` and its green
    `#4E8542` land dE 7.8 apart under deuteranopia, which is "the same colour
    with a bad print". If this ever stops being true the palette has been
    edited and `drp/viz/theme.py`'s docstring is now lying.
    """
    d, pair = cvd.min_separation(CHART.palette, "deuteranopia")
    assert d < 10.0
    assert set(pair) == {"#C0504D", "#4E8542"}
    assert cvd.min_separation(CHART.palette, "normal")[0] > 25.0, \
        "it is perfectly readable to normal vision, which is why it survived"


def test_the_chart_ramp_folds_back_under_deuteranopia():
    """The finding §2.5 did not expect. A sequential ramp has to be monotone in
    perceived distance from its own start, or a high value looks like a low
    one. `chart`'s teal -> amber -> magenta is not: its far end lands closer to
    its near end than its middle does.
    """
    stops = _sample_ramp(CHART.ramp, 9)
    d = [cvd.delta_e(cvd.simulate(c, "deuteranopia"),
                     cvd.simulate(stops[0], "deuteranopia")) for c in stops]
    assert d[-1] < max(d), "the chart ramp no longer folds back; update the docs"
    assert d[-1] < 15.0
    assert max(d) > 50.0


def _sample_ramp(stops, n: int):
    """`n` evenly spaced colours along a piecewise-linear ramp of hex stops."""
    rgb = [cvd.hex_to_rgb(s) for s in stops]
    out = []
    for i in range(n):
        t = i / (n - 1) * (len(rgb) - 1)
        lo = min(int(t), len(rgb) - 2)
        f = t - lo
        out.append(cvd.rgb_to_hex(
            [rgb[lo][k] + (rgb[lo + 1][k] - rgb[lo][k]) * f for k in range(3)]))
    return out


# ---------------------------------------------------------------------------
# the safe theme's claims
# ---------------------------------------------------------------------------
def test_the_safe_palette_stays_separable_under_every_deficiency():
    """The headline claim: worst pair dE 29.5, against `chart`'s 7.8."""
    for kind in ("normal",) + DEFICIENCIES:
        d, pair = cvd.min_separation(SAFE.palette, kind)
        assert d > 28.0, f"{kind}: {pair[0]} and {pair[1]} are only dE {d:.1f} apart"


def test_the_safe_palette_is_legible_on_the_page_background():
    """Separation is not enough on its own -- a pair of colours can be far
    apart from each other and both invisible against the paper."""
    for c in SAFE.palette:
        assert contrast_ratio(c, PAPER) >= 3.0, \
            f"{c} is only {contrast_ratio(c, PAPER):.2f}:1 against the paper"


def test_no_safe_colour_carries_two_meanings():
    """A route colour that is also a semantic colour would make "this drone"
    and "this breach" the same mark. The two sets are held apart on purpose."""
    semantic = [SAFE.accent, SAFE.success, SAFE.caution, SAFE.warn,
                SAFE.restricted]
    for kind in ("normal",) + DEFICIENCIES:
        for route in SAFE.palette:
            for sem in semantic:
                d = cvd.delta_e(cvd.simulate(route, kind), cvd.simulate(sem, kind))
                assert d > 10.0, \
                    f"{kind}: route {route} and semantic {sem} are dE {d:.1f} apart"


def test_the_semantics_that_appear_together_stay_apart():
    """Delivered, breached, restricted and timed-out can all be on one map at
    once, and "delivered green vs breach red" was the classic failure."""
    together = [SAFE.success, SAFE.caution, SAFE.warn, SAFE.restricted]
    for kind in ("normal",) + DEFICIENCIES:
        d, pair = cvd.min_separation(together, kind)
        # The binding pair is caution against warn under tritanopia, at 24.3 --
        # a red and an amber, which tritanopes compress towards each other.
        # Both also carry a distinct shape, so 22 is the floor asserted here
        # rather than a number the palette only just clears.
        assert d > 22.0, f"{kind}: {pair} only dE {d:.1f} apart"


def test_the_safe_ramp_is_monotone_under_every_deficiency():
    """What a sequential ramp actually needs, and what `chart`'s does not do."""
    stops = _sample_ramp(SAFE.ramp, 9)
    for kind in ("normal",) + DEFICIENCIES:
        d = [cvd.delta_e(cvd.simulate(c, kind), cvd.simulate(stops[0], kind))
             for c in stops]
        assert all(d[i + 1] > d[i] + 1.0 for i in range(len(d) - 1)), \
            f"{kind}: ramp is not monotone -- {[round(v, 1) for v in d]}"
        assert d[-1] > 60.0, f"{kind}: ramp spans only dE {d[-1]:.1f}"


def test_the_safe_method_colours_stay_separable_on_a_dashboard_panel():
    """Method curves are thin lines on a near-white panel, which is a stricter
    contrast test than a filled swatch on the paper."""
    cols = list(SAFE.method_colors.values())
    for kind in ("normal",) + DEFICIENCIES:
        d, pair = cvd.min_separation(cols, kind)
        assert d > 25.0, f"{kind}: {pair} only dE {d:.1f} apart"
    for c in cols:
        assert contrast_ratio(c, PANEL) >= 2.9, \
            f"{c} is only {contrast_ratio(c, PANEL):.2f}:1 on a dashboard panel"


# ---------------------------------------------------------------------------
# the second channel
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("theme", list(THEMES.values()), ids=lambda t: t.name)
def test_every_theme_carries_a_second_channel_per_series(theme: Theme):
    """No palette helps a monochromat, and none survives a fax. Colour is never
    the only carrier: index `i` is a colour *and* a dash *and* a marker."""
    n = len(theme.palette)
    assert len(theme.dashes) == n
    assert len(theme.markers) == n
    assert len(theme.hatches) == n
    assert len(set(theme.dashes)) == n, "two routes would share a dash pattern"
    assert len(set(theme.markers)) == n, "two routes would share a marker"
    assert len(set(theme.hatches)) == n, "two bars would share a hatch"


@pytest.mark.parametrize("theme", list(THEMES.values()), ids=lambda t: t.name)
def test_every_method_has_its_own_dash_and_marker(theme: Theme):
    assert len(set(theme.method_dashes.values())) == len(theme.method_dashes)
    assert len(set(theme.method_markers.values())) == len(theme.method_markers)


@pytest.mark.parametrize("theme", list(THEMES.values()), ids=lambda t: t.name)
def test_the_second_channel_is_the_same_in_both_themes(theme: Theme):
    """So a figure's *shapes* are comparable between the two, and switching
    theme changes only the colour."""
    assert theme.dashes == CHART.dashes
    assert theme.markers == CHART.markers
    assert theme.hatches == CHART.hatches


def test_svg_dash_patterns_convert_to_matplotlib_linestyles():
    assert CHART.mpl_dash(0) == "solid"
    on, off = CHART.mpl_dash(1)[1]
    assert on > 0 and off > 0
    assert CHART.method_mpl_dash("bnb") == "solid"
    assert isinstance(CHART.method_mpl_dash("ga"), tuple)


# ---------------------------------------------------------------------------
# selection and payload
# ---------------------------------------------------------------------------
def test_safe_is_the_default_and_chart_is_still_reachable():
    assert DEFAULT_THEME == "safe"
    assert get_theme("chart") is CHART
    assert get_theme("safe") is SAFE


def test_resolve_accepts_a_name_a_theme_or_none():
    assert resolve("chart") is CHART
    assert resolve(CHART) is CHART
    assert resolve(None) is active_theme()


def test_use_theme_switches_the_active_theme_and_can_be_switched_back():
    before = active_theme()
    try:
        assert use_theme("chart") is CHART
        assert active_theme() is CHART
        assert use_theme("safe") is SAFE
    finally:
        use_theme(before)


def test_an_unknown_theme_name_is_an_error():
    with pytest.raises(ValueError, match="unknown theme"):
        get_theme("dracula")


@pytest.mark.parametrize("theme", list(THEMES.values()), ids=lambda t: t.name)
def test_to_dict_is_json_serialisable_and_carries_what_a_page_needs(theme: Theme):
    import json

    d = theme.to_dict()
    json.loads(json.dumps(d))
    assert d["name"] == theme.name
    assert d["palette"] == list(theme.palette)
    assert d["dashes"] == list(theme.dashes)
    assert d["ramp"] == list(theme.ramp)
    for key in ("ink", "muted", "line", "paper", "panel", "accent", "accent2",
                "restricted", "caution", "warn", "success", "water"):
        assert d["tokens"][key].startswith("#")


@pytest.mark.parametrize("theme", list(THEMES.values()), ids=lambda t: t.name)
def test_cycles_wrap_rather_than_running_out(theme: Theme):
    n = len(theme.palette)
    assert theme.color(n) == theme.color(0)
    assert theme.dash(n + 1) == theme.dash(1)
    assert theme.marker(2 * n) == theme.marker(0)


def test_the_chart_theme_is_byte_for_byte_the_original_palette():
    """`--theme chart` exists so committed figures regenerate unchanged. That
    is only true if nobody has quietly improved it."""
    assert list(CHART.palette) == ["#2E75B6", "#C0504D", "#4E8542", "#8064A2",
                                   "#F79646", "#4BACC6"]
    assert CHART.method_colors == {"greedy": "#808080", "bnb": "#4E8542",
                                   "ga": "#2E75B6", "sa": "#C0504D",
                                   "alns": "#8064A2"}
    assert (CHART.restricted, CHART.caution, CHART.warn, CHART.success) == \
        ("#8E2F63", "#B23A22", "#9C6B12", "#3E7A3C")


def test_hex_round_trips():
    for c in list(SAFE.palette) + list(CHART.palette):
        assert cvd.rgb_to_hex(cvd.hex_to_rgb(c)) == c.upper()
    assert cvd.hex_to_rgb("#fff") == (1.0, 1.0, 1.0)
    with pytest.raises(ValueError):
        cvd.hex_to_rgb("#12345")


def test_switching_the_theme_actually_changes_what_is_drawn():
    """A "theme switch" that changed nothing visible would be worse than none.

    The claim is not that entry `i` moved -- the two palettes are not two
    versions of one design and their slots do not correspond -- but that no
    colour survived unchanged, and that the thing the switch exists for got
    several times better.
    """
    assert not (set(SAFE.palette) & set(CHART.palette))
    safe = cvd.min_separation(SAFE.palette, "deuteranopia")[0]
    chart = cvd.min_separation(CHART.palette, "deuteranopia")[0]
    assert safe > 3 * chart,         f"deuteranopia floor only went {chart:.1f} -> {safe:.1f}"
