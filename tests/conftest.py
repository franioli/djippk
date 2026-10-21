"""Synthetic flight: a straight 5 Hz trajectory (60 s) and an MRK with three photos."""

import stat
from pathlib import Path

import pandas as pd
import pytest

from gnsskit import GPS_EPOCH

T0 = pd.Timestamp("2026-09-06 12:00:00")  # GPST
T0_GPS_S = (T0 - GPS_EPOCH).total_seconds()
HEADER = (
    "% program   : RTKLIB test\n"
    "% ref pos   : 46.0 9.0 2000.0\n"
    "%\n"
    "%  GPST                  latitude(deg) longitude(deg)  height(m)   Q  ns   sdn(m)   sde(m)   sdu(m)  sdne(m)  sdeu(m)  sdun(m) age(s)  ratio\n"
)
# photo number, seconds after T0, N/E/V offsets in mm
PHOTOS = [(1, 2.5, 100, 50, 80), (2, 10.0, 100, 50, 80), (3, 35.9996, 100, 50, 80)]


def traj_line(s: float, q: int = 1) -> str:
    """One .pos epoch at s seconds after T0: lat/lon/h are linear in s."""
    t = T0 + pd.Timedelta(seconds=s)
    return (
        f"{t:%Y/%m/%d %H:%M:%S}.{t.microsecond // 1000:03d}"
        f"{46.0 + 1e-6 * s:15.9f}{9.0 + 2e-6 * s:15.9f}{2000.0 + 0.1 * s:11.4f}{q:4d}{12:4d}"
        f"{0.003:9.4f}{0.002:9.4f}{0.008:9.4f}{0.0:9.4f}{0.0:9.4f}{0.0:9.4f}{0.2:8.2f}{10.0:7.1f}\n"
    )


def mrk_text() -> str:
    week, tow0 = divmod(T0_GPS_S, 604800)
    return "".join(
        f"{n}\t{tow0 + s:.6f}\t[{int(week)}]\t{on:6d},N\t{oe:6d},E\t{ov:6d},V\t"
        f"46.0,Lat\t9.0,Lon\t2000.0,Ellh\t0.016, 0.010, 0.040\t50,Q\n"
        for n, s, on, oe, ov in PHOTOS
    )


@pytest.fixture
def pos_file(tmp_path: Path) -> Path:
    p = tmp_path / "flight_PPKOBS.pos"
    p.write_text(HEADER + "".join(traj_line(i * 0.2) for i in range(301)))
    return p


@pytest.fixture
def mrk_file(tmp_path: Path) -> Path:
    p = tmp_path / "flight_Timestamp.MRK"
    p.write_text(mrk_text())
    return p


@pytest.fixture
def fake_rnx2rtkp(tmp_path: Path) -> str:
    """An 'rnx2rtkp' that writes the synthetic trajectory to the -o path, ignoring its inputs."""
    traj = tmp_path / "traj.pos"
    traj.write_text(HEADER + "".join(traj_line(i * 0.2) for i in range(301)))
    exe = tmp_path / "fake_rnx2rtkp"
    exe.write_text(
        '#!/bin/sh\nwhile [ $# -gt 0 ]; do [ "$1" = "-o" ] && out="$2"; shift; done\n' f'cp "{traj}" "$out"\n'
    )
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return str(exe)
