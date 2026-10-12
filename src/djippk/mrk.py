"""Reader for DJI `*_Timestamp.MRK` files (one line per photo)."""

import re
from pathlib import Path

import pandas as pd

SECONDS_PER_WEEK = 604800


def _num(key: str, line: str) -> float:
    m = re.search(rf"([-+]?[\d.]+),{key}\b", line)
    if m is None:
        raise ValueError(f"field '{key}' not found in MRK line: {line.strip()}")
    return float(m.group(1))


def read_mrk(path: Path | str) -> pd.DataFrame:
    """Read an MRK file.

    Columns: `n` photo number, `gps_s` exposure time (s since the GPS epoch), `off_n/off_e/off_v`
    camera-antenna offsets [m] as listed by DJI, `lat/lon/h` the DJI position, `q` DJI quality flag.
    """
    rows = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        f = line.split()
        week = int(re.search(r"\[(\d+)\]", line).group(1))  # type: ignore[union-attr]
        rows.append({
            "n": int(f[0]),
            "gps_s": week * SECONDS_PER_WEEK + float(f[1]),
            "off_n": _num("N", line) / 1000,
            "off_e": _num("E", line) / 1000,
            "off_v": _num("V", line) / 1000,
            "lat": _num("Lat", line),
            "lon": _num("Lon", line),
            "h": _num("Ellh", line),
            "q": int(_num("Q", line)),
        })
    if not rows:
        raise ValueError(f"{path}: no photo lines found")
    return pd.DataFrame(rows)
