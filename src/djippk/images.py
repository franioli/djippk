"""DJI images of a flight and their match with the per-photo events."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from gnsskit import GPS_EPOCH

IMG_RE = re.compile(r"^DJI_(\d{14})_(\d{4})_([A-Z])\.(jpe?g|dng)$", re.IGNORECASE)
NAME_TOL_S = 1.5  # file names have 1 s resolution
EXPOSURE_TOL_S = 0.01  # events are written to 1 ms


def list_images(folder: Path | str, suffix: str = "V") -> pd.DataFrame:
    """Images `DJI_<time>_<NNNN>_<suffix>.*` in a folder, sorted by number.

    Columns: `n` photo number, `t_name` time from the file name (camera clock, 1 s), `name`, `path`.
    """
    rows = []
    for p in sorted(Path(folder).iterdir()):
        m = IMG_RE.match(p.name)
        if m and m.group(3).upper() == suffix.upper():
            rows.append((
                int(m.group(2)),
                pd.to_datetime(m.group(1), format="%Y%m%d%H%M%S"),
                p.name,
                p,
            ))
    return (
        pd
        .DataFrame(rows, columns=["n", "t_name", "name", "path"])
        .sort_values("n")
        .reset_index(drop=True)
    )


def exposure_times(paths: list[Path]) -> np.ndarray | None:
    """Exposure time of each image (s since GPS epoch) from the DJI XMP tag, or None if unavailable.

    The tag is named UTCAtExposure but its value is in GPS time: it matches the MRK time to the microsecond.
    """
    exe = shutil.which("exiftool")
    if exe is None or not paths:
        return None
    proc = subprocess.run(
        [exe, "-j", "-XMP-drone-dji:UTCAtExposure", *map(str, paths)],
        capture_output=True,
        text=True,
    )
    rows = {
        Path(r["SourceFile"]).name: r.get("UTCAtExposure")
        for r in json.loads(proc.stdout or "[]")
    }
    values = [rows.get(p.name) for p in paths]
    if any(v is None for v in values):
        return None
    t = pd.to_datetime(pd.Series(values), format="%Y:%m:%d %H:%M:%S.%f")
    return ((t - GPS_EPOCH).dt.total_seconds()).to_numpy()


def check_match(
    img: pd.DataFrame, ev: pd.DataFrame, exposure_s: np.ndarray | None = None
) -> list[str]:
    """Problems between images and events (empty list if they match).

    Structure: one image per number, numbers 1..N, N equal to the number of events. Timing: the XMP exposure time
    of each image must equal its event time; without XMP, the time between consecutive photos in the file names
    must equal the one between the events.
    """
    if img.empty:
        return ["no images found (check the folder and --suffix)"]
    problems = []
    dup = img["n"][img["n"].duplicated()].unique()
    if len(dup):
        problems.append(
            f"more than one image for numbers {dup.tolist()[:10]} (e.g. JPG and DNG)"
        )
    if len(img) != len(ev):
        problems.append(
            f"{len(img)} images but {len(ev)} events (events skipped because outside the trajectory?)"
        )
    missing = sorted(set(range(1, int(img["n"].max()) + 1)) - set(img["n"]))
    if missing:
        problems.append(f"image numbers missing: {missing[:20]}")
    if problems:
        return problems

    ev_s = ev["gps_s"].to_numpy()
    if exposure_s is not None:
        bad = np.where(np.abs(exposure_s - ev_s) > EXPOSURE_TOL_S)[0]
        for i in bad[:10]:
            problems.append(
                f"photo {img['n'][i]}: exposure time in the image differs from the event by {exposure_s[i] - ev_s[i]:+.3f} s"
            )
    else:
        d_name = img["t_name"].diff().dt.total_seconds().to_numpy()[1:]
        bad = np.where(np.abs(d_name - np.diff(ev_s)) > NAME_TOL_S)[0]
        for i in bad[:10]:
            problems.append(
                f"time between photos {img['n'][i]} and {img['n'][i + 1]}: {d_name[i]:.0f} s in file names, "
                f"{np.diff(ev_s)[i]:.1f} s in events"
            )
    return problems
