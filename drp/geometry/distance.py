"""Distance metrics.

Euclidean for synthetic instances, haversine for lat/lon ones. Both return a
plain dense matrix so the rest of the package is metric-agnostic.
"""
from __future__ import annotations

import numpy as np

EARTH_RADIUS_KM = 6371.0088


def euclidean_matrix(coords: np.ndarray) -> np.ndarray:
    diff = coords[:, None, :] - coords[None, :, :]
    return np.sqrt((diff ** 2).sum(axis=2))


def haversine_matrix(coords: np.ndarray) -> np.ndarray:
    """Great-circle distance in kilometres. `coords` is ``(lat, lon)`` degrees."""
    lat = np.radians(coords[:, 0])
    lon = np.radians(coords[:, 1])
    dlat = lat[:, None] - lat[None, :]
    dlon = lon[:, None] - lon[None, :]
    a = (np.sin(dlat / 2) ** 2
         + np.cos(lat)[:, None] * np.cos(lat)[None, :] * np.sin(dlon / 2) ** 2)
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def distance_matrix(coords: np.ndarray, geodesic: bool = False) -> np.ndarray:
    return haversine_matrix(coords) if geodesic else euclidean_matrix(coords)
