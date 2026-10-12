"""Image coordinates: a plain-text reference file for Metashape, and optionally GPS tags written into the images."""

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


def build_reference(
    img: pd.DataFrame, ev: pd.DataFrame, min_acc: float = 0.03, keep_ext: bool = False
) -> pd.DataFrame:
    """One row per image: label, lon, lat, alt (ellipsoidal), accuracies (floored at min_acc, m) and Q."""
    return pd.DataFrame({
        "label": img["name"] if keep_ext else img["name"].str.rsplit(".", n=1).str[0],
        "lon": ev["lon"].to_numpy(),
        "lat": ev["lat"].to_numpy(),
        "alt": ev["h"].to_numpy(),
        "acc_E": np.maximum(ev["sde"].to_numpy(), min_acc),
        "acc_N": np.maximum(ev["sdn"].to_numpy(), min_acc),
        "acc_h": np.maximum(ev["sdu"].to_numpy(), min_acc),
        "Q": ev["Q"].to_numpy().astype(int),
    })


def write_reference(ref: pd.DataFrame, path: Path) -> Path:
    """Comma-separated text file, header line starting with `#` (Metashape skips it; map columns in the dialog)."""
    lines = ["# " + ",".join(ref.columns)]
    for r in ref.itertuples(index=False):
        lines.append(
            f"{r.label},{r.lon:.9f},{r.lat:.9f},{r.alt:.4f},{r.acc_E:.3f},{r.acc_N:.3f},{r.acc_h:.3f},{r.Q}"
        )
    path.write_text("\n".join(lines) + "\n")
    return path


def exiftool_args(path: Path, r: pd.Series) -> list[str]:
    """exiftool arguments (numeric values) setting the EXIF GPS tags and the DJI XMP position and RTK std tags."""
    return [
        f"-GPSLatitude={abs(r['lat']):.9f}",
        f"-GPSLatitudeRef={'N' if r['lat'] >= 0 else 'S'}",
        f"-GPSLongitude={abs(r['lon']):.9f}",
        f"-GPSLongitudeRef={'E' if r['lon'] >= 0 else 'W'}",
        f"-GPSAltitude={abs(r['h']):.4f}",
        f"-GPSAltitudeRef={0 if r['h'] >= 0 else 1}",
        f"-XMP-drone-dji:GPSLatitude={r['lat']:.9f}",
        f"-XMP-drone-dji:GPSLongitude={r['lon']:.9f}",
        f"-XMP-drone-dji:AbsoluteAltitude={r['h']:.4f}",
        f"-XMP-drone-dji:RtkStdLat={r['sdn']:.5f}",
        f"-XMP-drone-dji:RtkStdLon={r['sde']:.5f}",
        f"-XMP-drone-dji:RtkStdHgt={r['sdu']:.5f}",
        str(path),
    ]


def write_exif(paths: list[Path], ev: pd.DataFrame, backup: bool = True) -> None:
    """Write the event positions into the images with one exiftool run.

    Tags: EXIF GPS latitude, longitude, altitude (ellipsoidal height) and the DJI XMP position and RTK std tags,
    the same ones Emlid Studio writes. With `backup`, exiftool keeps `<image>_original` copies.
    """
    exe = shutil.which("exiftool")
    if exe is None:
        raise FileNotFoundError(
            "exiftool not found on PATH; it is needed to write image tags (https://exiftool.org)"
        )
    lines: list[str] = []
    for path, (_, r) in zip(paths, ev.iterrows()):
        lines += ([] if not lines else ["-execute"]) + exiftool_args(path, r)
    # options shared by all the per-image commands go after -common_args, at the end of the argument file
    lines += ["-common_args", "-n", "-P", "-m"] + (
        [] if backup else ["-overwrite_original"]
    )
    with tempfile.TemporaryDirectory() as tmp:
        argfile = Path(tmp) / "args.txt"
        argfile.write_text("\n".join(lines) + "\n")
        proc = subprocess.run([exe, "-@", str(argfile)], capture_output=True, text=True)
    if proc.returncode != 0 or "error" in proc.stderr.lower():
        raise RuntimeError(
            f"exiftool failed: {(proc.stderr or proc.stdout).strip()[-500:]}"
        )
