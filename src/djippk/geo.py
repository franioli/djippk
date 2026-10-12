"""Small-area geodetic helpers (GRS80/WGS84, differences between the two are sub-mm here)."""

import numpy as np
import pandas as pd

A = 6378137.0
E2 = 0.00669438


def radii(
    lat_deg: pd.Series | np.ndarray, h: pd.Series | np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Meridian and prime-vertical radii plus height, in metres: (Rm + h, (Rn + h) cos(lat))."""
    phi = np.radians(np.asarray(lat_deg, dtype=float))
    w = np.sqrt(1 - E2 * np.sin(phi) ** 2)
    h = np.asarray(h, dtype=float)
    return A * (1 - E2) / w**3 + h, (A / w + h) * np.cos(phi)


def enu_diff(
    lat: pd.Series,
    lon: pd.Series,
    h: pd.Series,
    lat0: pd.Series,
    lon0: pd.Series,
    h0: pd.Series,
) -> np.ndarray:
    """(E, N, U) offsets in metres of points (lat, lon, h) from reference points (lat0, lon0, h0)."""
    rm, rn = radii(lat0, h0)
    e = np.radians(np.asarray(lon, dtype=float) - np.asarray(lon0, dtype=float)) * rn
    n = np.radians(np.asarray(lat, dtype=float) - np.asarray(lat0, dtype=float)) * rm
    u = np.asarray(h, dtype=float) - np.asarray(h0, dtype=float)
    return np.column_stack([e, n, u])
