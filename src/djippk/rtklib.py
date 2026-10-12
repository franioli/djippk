"""Thin wrapper around RTKLIB rnx2rtkp: kinematic configuration, execution and .pos parsing."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

GPS_EPOCH = pd.Timestamp("1980-01-06")

POS_COLS = [
    "date", "time", "lat", "lon", "h", "Q", "ns",
    "sdn", "sde", "sdu", "sdne", "sdeu", "sdun", "age", "ratio",
]  # fmt: skip

# Kinematic, dual-frequency, short-baseline defaults (GPS+GAL+BDS, GLONASS AR off), forward+backward.
DEFAULT_OPTIONS: dict[str, str] = {
    "pos1-posmode": "kinematic",
    "pos1-frequency": "l1+l2",
    "pos1-soltype": "combined",
    "pos1-elmask": "15",
    "pos1-snrmask_r": "off",
    "pos1-snrmask_b": "off",
    "pos1-dynamics": "off",
    "pos1-ionoopt": "brdc",
    "pos1-tropopt": "saas",
    "pos1-sateph": "brdc",
    "pos1-navsys": "41",
    "pos2-armode": "continuous",
    "pos2-gloarmode": "off",
    "pos2-bdsarmode": "on",
    "pos2-arthres": "3.0",
    "pos2-arlockcnt": "0",
    "pos2-arelmask": "15",
    "misc-timeinterp": "on",
    "ant1-postype": "llh",
    "ant1-anttype": "",
    "ant2-anttype": "",
    "ant2-antdele": "0",
    "ant2-antdeln": "0",
    "ant2-antdelu": "0",
    "out-solformat": "llh",
    "out-outhead": "on",
    "out-outopt": "on",
    "out-timesys": "gpst",
    "out-timeform": "hms",
    "out-timendec": "3",
    "out-degform": "deg",
    "out-height": "ellipsoidal",
    "out-geoid": "internal",
}

RTKLIB_URL = "https://github.com/rtklibexplorer/RTKLIB"


def install_hint() -> str:
    """How to install rnx2rtkp on the current platform."""
    if sys.platform == "win32":
        return (
            f"Download an RTKLIB release (demo5 recommended: {RTKLIB_URL}/releases), unzip it, and add "
            "the folder containing rnx2rtkp.exe to your PATH, or pass --exe C:\\path\\to\\rnx2rtkp.exe."
        )
    return (
        f"Build it from source (demo5 recommended):\n"
        f"  git clone {RTKLIB_URL}\n"
        "  cd RTKLIB/app/consapp/rnx2rtkp/gcc && make && sudo make install\n"
        "or copy the binary to a folder on your PATH. Alternatively pass --exe /path/to/rnx2rtkp."
    )


def find_rnx2rtkp(exe: str = "rnx2rtkp") -> str:
    """Resolve the rnx2rtkp executable; raise FileNotFoundError with install hints if missing."""
    path = shutil.which(exe)
    if path is None:
        raise FileNotFoundError(f"'{exe}' not found on PATH. {install_hint()}")
    return path


@dataclass(frozen=True)
class RtkConfig:
    """Immutable set of rnx2rtkp options (keys as in RTKLIB .conf files)."""

    options: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_OPTIONS))

    @classmethod
    def from_file(cls, path: Path) -> RtkConfig:
        """Load an RTKLIB .conf file on top of DEFAULT_OPTIONS."""
        opts = dict(DEFAULT_OPTIONS)
        for line in path.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                key, value = line.split("=", 1)
                opts[key.strip()] = value.strip()
        return cls(opts)

    def updated(self, overrides: Mapping[str, object]) -> RtkConfig:
        return RtkConfig({**self.options, **{k: str(v) for k, v in overrides.items()}})

    def with_base(
        self, lat: float, lon: float, h: float, antenna_h: float = 0.0
    ) -> RtkConfig:
        """Fix the base at (lat, lon, ellipsoidal h) with the antenna `antenna_h` metres above that point."""
        return self.updated({
            "ant2-postype": "llh",
            "ant2-pos1": f"{lat:.10f}",
            "ant2-pos2": f"{lon:.10f}",
            "ant2-pos3": f"{h:.5f}",
            "ant2-antdelu": f"{antenna_h:.4f}",
        })

    def to_text(self) -> str:
        return "".join(f"{k:<19}={v}\n" for k, v in self.options.items())

    def write(self, path: Path) -> Path:
        path.write_text(self.to_text())
        return path


def read_base_position(path: Path) -> tuple[float, float, float]:
    """Base (lat, lon, h) from a CSV with header `latitude(deg),longitude(deg),height(m)` and one row."""
    df = pd.read_csv(path)
    if len(df) < 1 or df.shape[1] < 3:
        raise ValueError(f"{path}: expected a header and one row with lat, lon, height")
    lat, lon, h = df.iloc[0, :3].astype(float)
    return float(lat), float(lon), float(h)


def build_command(
    conf: Path,
    rover: Path,
    base: Path,
    nav: Sequence[Path],
    out: Path,
    exe: str = "rnx2rtkp",
) -> list[str]:
    """rnx2rtkp command line: rover observations first, then base observations, then navigation files."""
    return [exe, "-k", str(conf), "-o", str(out), str(rover), str(base), *map(str, nav)]


def run_rnx2rtkp(
    rover: Path,
    base: Path,
    nav: Sequence[Path],
    config: RtkConfig,
    out: Path,
    exe: str = "rnx2rtkp",
) -> Path:
    """Run rnx2rtkp and return the output .pos path; raise if it fails or produces no epochs."""
    exe = find_rnx2rtkp(exe)
    with tempfile.TemporaryDirectory() as tmp:
        conf = config.write(Path(tmp) / "rtk.conf")
        proc = subprocess.run(
            build_command(conf, rover, base, nav, out, exe),
            capture_output=True,
            text=True,
        )
    if proc.returncode != 0:
        raise RuntimeError(
            f"rnx2rtkp failed ({proc.returncode}): {proc.stderr.strip()[-500:]}"
        )
    if not out.exists() or not any(
        not ln.startswith("%") for ln in out.read_text().splitlines()
    ):
        raise RuntimeError(
            f"rnx2rtkp produced no solution epochs in {out} (check time overlap of rover and base)"
        )
    return out


def read_pos(path: Path | str) -> pd.DataFrame:
    """Read an RTKLIB llh .pos (GPST, decimal degrees) into a DataFrame with `t` (GPST) and `gps_s`.

    `gps_s` is seconds since the GPS epoch (1980-01-06), which avoids week roll-over problems.
    """
    path = Path(path)
    df = pd.read_csv(path, comment="%", sep=r"\s+", header=None, names=POS_COLS)
    if df.empty:
        raise ValueError(
            f"{path} has no data lines (only a header). Give the trajectory <flight>_PPKOBS.pos, "
            "not the empty <flight>_PPKOBS_events.pos written by rnx2rtkp."
        )
    df["t"] = pd.to_datetime(df["date"] + " " + df["time"])
    df["gps_s"] = (df["t"] - GPS_EPOCH).dt.total_seconds()
    return df


def read_header(path: Path | str) -> list[str]:
    """The `%` header lines of a .pos file (without line endings)."""
    return [
        ln.rstrip("\r\n")
        for ln in Path(path).read_text().splitlines()
        if ln.startswith("%")
    ]


def rinex_span(obs: Path | str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """First and last epoch (GPST) of a RINEX 3 observation file; raise ValueError if none found."""
    first = last = None
    with Path(obs).open() as f:
        for line in f:
            if not line.startswith(">"):
                continue
            try:
                y, mo, d, h, mi, s = line[1:].split()[:6]
                last = pd.Timestamp(
                    int(y), int(mo), int(d), int(h), int(mi)
                ) + pd.Timedelta(seconds=float(s))
            except ValueError:
                continue
            if first is None:
                first = last
    if first is None or last is None:
        raise ValueError(f"no RINEX 3 epochs found in {obs}")
    return first, last
