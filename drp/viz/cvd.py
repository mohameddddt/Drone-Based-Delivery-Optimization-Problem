"""Colour-vision-deficiency simulation, so a palette claim can be checked.

`PROGRESS.md` §2.5 asks for a colour-blind-safe theme. "Safe" is only a claim
until something measures it, so this module implements the standard simulation
and the standard distance metric, and `tests/test_viz_theme.py` runs both over
every theme the package ships.

The simulation is Viénot, Brettel & Mollon (1999) for protanopia and
deuteranopia -- projection onto the dichromat's reduced colour plane in LMS --
and Brettel, Viénot & Mollon (1997) for tritanopia, which is not well modelled
by the single-plane form. Transfer in and out of sRGB is done through the
proper gamma curve rather than on the encoded bytes; skipping that is the usual
reason a hand-rolled simulator disagrees with the published ones.

Distances are CIE76 dE*ab in CIELAB. dE is used comparatively here -- "does
this pair stay as separable as it started" -- not as an absolute threshold.
"""
from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

import numpy as np

KINDS = ("normal", "protanopia", "deuteranopia", "tritanopia")

# sRGB (linear) -> LMS, Hunt-Pointer-Estevez normalised to D65, as used by
# Viénot et al. Their paper works in this space throughout.
_RGB2LMS = np.array([
    [0.31399022, 0.63951294, 0.04649755],
    [0.15537241, 0.75789446, 0.08670142],
    [0.01775239, 0.10944209, 0.87256922],
])
_LMS2RGB = np.linalg.inv(_RGB2LMS)

# Viénot 1999 single-plane projections (LMS), Table 1.
_PROTAN = np.array([
    [0.0, 1.05118294, -0.05116099],
    [0.0, 1.0, 0.0],
    [0.0, 0.0, 1.0],
])
_DEUTAN = np.array([
    [1.0, 0.0, 0.0],
    [0.9513092, 0.0, 0.04264257],
    [0.0, 0.0, 1.0],
])
# Brettel 1997 tritanopia: two half-planes, hinged on the neutral axis. Which
# half applies depends on which side of the plane through E and the two anchor
# stimuli the colour falls.
_TRITAN_A = np.array([
    [1.0, 0.0, 0.0],
    [0.0, 1.0, 0.0],
    [-0.86744736, 1.86727089, 0.0],
])
_TRITAN_B = np.array([
    [1.0, 0.0, 0.0],
    [0.0, 1.0, 0.0],
    [0.15374045, -0.15310494, 0.0],
])


def _srgb_to_linear(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=float)
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(a: np.ndarray) -> np.ndarray:
    a = np.clip(np.asarray(a, dtype=float), 0.0, 1.0)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * a ** (1 / 2.4) - 0.055)


def hex_to_rgb(h: str) -> Tuple[float, float, float]:
    """`"#2E75B6"` or `"2e75b6"` -> three floats in [0, 1]."""
    s = h.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        raise ValueError(f"not a hex colour: {h!r}")
    return tuple(int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hex(rgb: Sequence[float]) -> str:
    return "#" + "".join(f"{int(round(min(max(c, 0.0), 1.0) * 255)):02X}" for c in rgb[:3])


def simulate_array(rgb: np.ndarray, kind: str) -> np.ndarray:
    """Simulate `kind` over an array of sRGB values in [0, 1], shape (..., 3)."""
    if kind == "normal":
        return np.asarray(rgb, dtype=float)
    if kind not in KINDS:
        raise ValueError(f"unknown deficiency {kind!r}; expected one of {KINDS}")

    lin = _srgb_to_linear(rgb)
    lms = lin @ _RGB2LMS.T

    if kind == "protanopia":
        out = lms @ _PROTAN.T
    elif kind == "deuteranopia":
        out = lms @ _DEUTAN.T
    else:
        # Brettel's hinge: compare against the plane spanned by the neutral
        # axis and the 475 nm anchor.
        lhs = lms[..., 0] * 0.34478 - lms[..., 1] * 0.65518
        a = lms @ _TRITAN_A.T
        b = lms @ _TRITAN_B.T
        out = np.where((lhs >= 0)[..., None], a, b)

    return _linear_to_srgb(out @ _LMS2RGB.T)


def simulate(color: str, kind: str) -> str:
    """Simulate `kind` over one hex colour, returning a hex colour."""
    return rgb_to_hex(simulate_array(np.array(hex_to_rgb(color)), kind))


def _to_lab(rgb: np.ndarray) -> np.ndarray:
    lin = _srgb_to_linear(rgb)
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    e, k = 216 / 24389, 24389 / 27
    f = np.where(xyz > e, np.cbrt(xyz), (k * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16,
                     500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], axis=-1)


def delta_e(a: str, b: str) -> float:
    """CIE76 dE*ab between two hex colours."""
    la, lb = _to_lab(np.array([hex_to_rgb(a), hex_to_rgb(b)]))
    return float(np.linalg.norm(la - lb))


def min_separation(colors: Sequence[str], kind: str) -> Tuple[float, Tuple[str, str]]:
    """The closest pair in `colors` under `kind`, and that pair.

    This is the number that decides whether a categorical palette works: a
    palette is only as good as its worst pair.
    """
    sims = [simulate(c, kind) for c in colors]
    worst, pair = float("inf"), (colors[0], colors[0])
    for i in range(len(colors)):
        for j in range(i + 1, len(colors)):
            d = delta_e(sims[i], sims[j])
            if d < worst:
                worst, pair = d, (colors[i], colors[j])
    return worst, pair


def separation_table(colors: Sequence[str]) -> List[Tuple[str, float, Tuple[str, str]]]:
    """`min_separation` for every kind, for reporting."""
    return [(k, *min_separation(colors, k)) for k in KINDS]


def simulate_image(src, dst, kind: str) -> None:
    """Write `src` (any PIL-readable image) simulated as `kind` to `dst`.

    Used to check the rendered pages and figures rather than only the palette
    they were built from -- a palette can be safe while a page still leans on
    a red/green pair the palette never named.
    """
    from PIL import Image

    im = Image.open(src).convert("RGB")
    arr = np.asarray(im, dtype=float) / 255.0
    out = simulate_array(arr, kind)
    Image.fromarray((np.clip(out, 0, 1) * 255).round().astype("uint8")).save(dst)


def simulate_images(paths: Iterable, out_dir, kinds: Sequence[str] = KINDS) -> List:
    """Batch `simulate_image` -- `<stem>.<kind>.png` for each input and kind."""
    from pathlib import Path

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for p in paths:
        p = Path(p)
        for k in kinds:
            if k == "normal":
                continue
            d = out_dir / f"{p.stem}.{k}.png"
            simulate_image(p, d, k)
            written.append(d)
    return written
