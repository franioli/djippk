"""Reading the PPK trajectory (`.pos`) and the events file."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from gnsskit import read_pos


def read_trajectory(path: Path | str) -> pd.DataFrame:
    """Read a decimal-degree llh `.pos` file; raise ValueError if it has no solution epochs.

    Args:
        path: Trajectory or events `.pos` file.

    Returns:
        The `gnsskit.read_pos` table, with `t` (GPST) and `gps_s`.

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
