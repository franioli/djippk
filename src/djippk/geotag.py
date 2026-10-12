"""Image coordinates: a plain-text reference file for Metashape, and optionally GPS tags written into the images."""

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


def build_reference(
    img: pd.DataFrame, ev: pd.DataFrame, min_acc: float = 0.03, keep_ext: bool = True
) -> pd.DataFrame:
    """One row per image: label (file name, with extension unless `keep_ext` is False), lon, lat, alt (ellipsoidal),
    accuracies (floored at min_acc, m) and Q."""
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


def write_exif(paths: list[Path], ev: pd.DataFrame, out_dir: Path | None = None) -> list[Path]:
    """Write the event positions into images with one exiftool run, and return the tagged files.

    Tags: EXIF GPS latitude, longitude, altitude (ellipsoidal height) and the DJI XMP position and RTK std tags,
    the same ones Emlid Studio writes. With `out_dir` the images are first copied there (same file names) and
    only the copies are tagged; with `out_dir=None` the input images are modified in place. No `*_original`
    backups are created.
    """
    exe = shutil.which("exiftool")
    if exe is None:
        raise FileNotFoundError(
            "exiftool not found on PATH; it is needed to write image tags (https://exiftool.org)"
        )
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        if out_dir.resolve() == paths[0].resolve().parent:
            raise ValueError(f"{out_dir} is the image folder: choose another folder, or overwrite the images explicitly")
        targets = [Path(shutil.copy2(p, out_dir / p.name)) for p in paths]
    else:
        targets = list(paths)
    # exiftool options go in every command: -common_args would apply to the last command only
    opts = ["-n", "-P", "-m", "-overwrite_original"]
    lines: list[str] = []
    for path, (_, r) in zip(targets, ev.iterrows()):
        lines += ([] if not lines else ["-execute"]) + opts + exiftool_args(path, r)
    with tempfile.TemporaryDirectory() as tmp:
        argfile = Path(tmp) / "args.txt"
        argfile.write_text("\n".join(lines) + "\n")
        proc = subprocess.run([exe, "-@", str(argfile)], capture_output=True, text=True)
    if proc.returncode != 0 or "error" in proc.stderr.lower():
        raise RuntimeError(
            f"exiftool failed: {(proc.stderr or proc.stdout).strip()[-500:]}"
        )
    return targets
