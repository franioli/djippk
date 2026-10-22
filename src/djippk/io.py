"""Readers for the inputs of a DJI flight: flight folder, MRK, PPK trajectory and base position."""

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from gnsskit import read_pos

SECONDS_PER_WEEK = 604800


@dataclass(frozen=True)
class Flight:
    """Files of one flight; `mrk` is None if the folder has no `*_Timestamp.MRK`."""

    obs: Path
    nav: Path
    mrk: Path | None

    @property
    def stem(self) -> Path:
        """Output prefix next to the rover RINEX: `<flight>_PPKOBS`."""
        return self.obs.with_suffix("")


def find_flights(paths: list[Path]) -> list[Flight]:
    """Flights found under the given folders (searched recursively) or given directly as `*_PPKOBS.obs` files.

    Each flight needs a `*_PPKNAV.nav` beside its observations; the MRK is optional.
    """
    obs_files: list[Path] = []
    for p in paths:
        obs_files += [p] if p.is_file() else sorted(p.rglob("*_PPKOBS.obs"))
    if not obs_files:
        raise FileNotFoundError("no *_PPKOBS.obs found in the given paths")
    flights = []
    for obs in obs_files:
        prefix = obs.name.removesuffix("_PPKOBS.obs")
        nav = obs.with_name(f"{prefix}_PPKNAV.nav")
        if not nav.exists():
            raise FileNotFoundError(f"missing navigation file {nav}")
        mrk = obs.with_name(f"{prefix}_Timestamp.MRK")
        flights.append(Flight(obs, nav, mrk if mrk.exists() else None))
    return flights


def _num(key: str, line: str) -> float:
    m = re.search(rf"([-+]?[\d.]+),{key}\b", line)
    if m is None:
        raise ValueError(f"field '{key}' not found in MRK line: {line.strip()}")
    return float(m.group(1))


def read_mrk(path: Path | str) -> pd.DataFrame:
    """Read a DJI `*_Timestamp.MRK` file (one line per photo).

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


def read_trajectory(path: Path | str) -> pd.DataFrame:
    """Read a decimal-degree llh `.pos` file (trajectory or events), with `t` (GPST) and `gps_s`.

    Raises:
        ValueError: If the file is not in llh format or has only a header.
    """
    pos = read_pos(path)
    if pos.attrs["format"] != "llh":
        raise ValueError(f"{path}: need out-solformat=llh, got {pos.attrs['format']}")
    if pos.empty:
        raise ValueError(
            f"{path} has no data lines (no solution epochs, only a header). "
            "Give the trajectory <flight>_PPKOBS.pos, not the empty <flight>_PPKOBS_events.pos "
            "written by rnx2rtkp."
        )
    return pos


def read_base_position(path: Path) -> tuple[float, float, float]:
    """Base (lat, lon, h) from a CSV with a header and one row: lat [deg], lon [deg], h [m]."""
    df = pd.read_csv(path)
    if len(df) < 1 or df.shape[1] < 3:
        raise ValueError(f"{path}: expected a header and one row with lat, lon, height")
    lat, lon, h = df.iloc[0, :3].astype(float)
    return lat, lon, h
