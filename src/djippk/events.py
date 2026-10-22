"""Per-photo positions: interpolate the PPK trajectory at the MRK exposure times and write `_events.pos`.

The events file has the layout Emlid Studio writes: the header of the `.pos` followed by one line per photo, in
shooting order, with the camera-antenna offsets from the MRK already applied.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from gnsskit.geodesy import radii
from gnsskit.trajectory import interpolate


def apply_offsets(
    ev: pd.DataFrame, off_n: np.ndarray, off_e: np.ndarray, off_v: np.ndarray
) -> pd.DataFrame:
    """Move antenna positions to the camera: N added to the northing, E to the easting, V subtracted from h.

    This is the convention of Emlid Studio, reproduced to within 3 mm on a test flight.
    """
    ev = ev.copy()
    rm, rn = radii(ev["lat"], ev["h"])
    ev["lat"] += np.degrees(off_n / rm)
    ev["lon"] += np.degrees(off_e / rn)
    ev["h"] -= off_v
    return ev


def build_events(
    pos: pd.DataFrame, mrk: pd.DataFrame, offsets: bool = True
) -> tuple[pd.DataFrame, list[int]]:
    """Events for every photo inside the trajectory, plus the numbers of the photos that were skipped."""
    inside = (
        (mrk["gps_s"] >= pos["gps_s"].iloc[0]) & (mrk["gps_s"] <= pos["gps_s"].iloc[-1])
    ).to_numpy()
    skipped = mrk["n"][~inside].tolist()
    m = mrk[inside]
    ev = interpolate(pos, m["gps_s"].to_numpy())
    if offsets:
        ev = apply_offsets(
            ev, m["off_n"].to_numpy(), m["off_e"].to_numpy(), m["off_v"].to_numpy()
        )
    ev.insert(0, "n", m["n"].to_numpy())
    return ev, skipped


def format_line(r: pd.Series) -> str:
    t = r["t"].round(
        "ms"
    )  # round before splitting, else 35.9996 s would print as 35.000
    return (
        f"{t:%Y/%m/%d %H:%M:%S}.{t.microsecond // 1000:03d}"
        f"{r['lat']:15.9f}{r['lon']:15.9f}{r['h']:11.4f}{int(r['Q']):4d}{int(r['ns']):4d}"
        f"{r['sdn']:9.4f}{r['sde']:9.4f}{r['sdu']:9.4f}{r['sdne']:9.4f}{r['sdeu']:9.4f}{r['sdun']:9.4f}"
        f"{r['age']:8.2f}{r['ratio']:7.1f}"
    )


def write_events(path: Path, ev: pd.DataFrame, header: list[str], source: str) -> Path:
    """Write an events file: a program line, the `.pos` header (without its program line), one line per photo."""
    lines = [f"% program   : djippk (interpolated from {source})"]
    lines += [ln for ln in header if not ln.startswith("% program")]
    lines += [format_line(r) for _, r in ev.iterrows()]
    path.write_text("\n".join(lines) + "\n")
    return path

