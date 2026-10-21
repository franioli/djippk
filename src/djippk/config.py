"""Default RTKLIB configuration for kinematic PPK of a drone, and the base position file."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from gnsskit import RtkConfig

# Kinematic, dual-frequency, short-baseline (GPS+Galileo+BeiDou, GLONASS AR off), forward+backward.
# Built from `empty()` so that only the options below are written to the .conf file.
DEFAULT_CONFIG = RtkConfig.empty().updated(
    posmode="kinematic",
    frequency="l1+l2",
    soltype="combined",
    elmask=15.0,
    snrmask_r=False,
    snrmask_b=False,
    dynamics=False,
    ionoopt="brdc",
    tropopt="saas",
    sateph="brdc",
    navsys="GEC",
    armode="continuous",
    gloarmode="off",
    bdsarmode=True,
    arthres=3.0,
    arlockcnt=0,
    arelmask=15.0,
    timeinterp=True,
    rover_postype="llh",
    rover_anttype="",
    base_anttype="",
    base_antdel=(0.0, 0.0, 0.0),
    solformat="llh",
    outhead=True,
    outopt=True,
    timesys="gpst",
    timeform="hms",
    timendec=3,
    degform="deg",
    height="ellipsoidal",
    geoid="internal",
)


def read_base_position(path: Path) -> tuple[float, float, float]:
    """Base (lat, lon, h) from a CSV with a header and one row: lat [deg], lon [deg], h [m]."""
    df = pd.read_csv(path)
    if len(df) < 1 or df.shape[1] < 3:
        raise ValueError(f"{path}: expected a header and one row with lat, lon, height")
    lat, lon, h = df.iloc[0, :3].astype(float)
    return float(lat), float(lon), float(h)
