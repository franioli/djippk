import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from djippk import events, geotag, images, mrk, rtklib


def make_images(folder: Path, offsets_s: list[int]) -> None:
    """Empty files named like DJI images, with the given file-name times (s after 14:00:00 local)."""
    for i, s in enumerate(offsets_s, start=1):
        t = pd.Timestamp("2026-09-06 14:00:00") + pd.Timedelta(seconds=s)
        (folder / f"DJI_{t:%Y%m%d%H%M%S}_{i:04d}_V.JPG").write_bytes(b"")


@pytest.fixture
def ev(pos_file, mrk_file):
    return events.build_events(rtklib.read_pos(pos_file), mrk.read_mrk(mrk_file))[0]


def test_list_images_and_match(tmp_path, ev):
    make_images(tmp_path, [2, 10, 36])  # same spacing as the events (7.5 s and 26 s)
    (tmp_path / "notes.txt").write_text("x")
    img = images.list_images(tmp_path)
    assert img["n"].tolist() == [1, 2, 3]
    # spacing in the names (8 s, 26 s) vs events (7.5 s, 26 s) is within the 1 s resolution
    assert images.check_match(img, ev) == []


def test_match_detects_missing_image_and_wrong_timing(tmp_path, ev):
    make_images(tmp_path, [2, 10])
    assert any("2 images but 3 events" in p for p in images.check_match(images.list_images(tmp_path), ev))
    for f in tmp_path.iterdir():
        f.unlink()
    make_images(tmp_path, [2, 10, 50])  # third photo 14 s late
    assert any("time between photos" in p for p in images.check_match(images.list_images(tmp_path), ev))


def test_match_with_exposure_times(tmp_path, ev):
    make_images(tmp_path, [2, 10, 36])
    img = images.list_images(tmp_path)
    good = ev["gps_s"].to_numpy()
    assert images.check_match(img, ev, good) == []
    assert any("photo 2" in p for p in images.check_match(img, ev, good + [0, 0.5, 0]))


def test_reference_file(tmp_path, ev):
    make_images(tmp_path, [2, 10, 36])
    img = images.list_images(tmp_path)
    ref = geotag.build_reference(img, ev)
    out = geotag.write_reference(ref, tmp_path / "ref.csv")
    lines = out.read_text().splitlines()
    assert lines[0] == "# label,lon,lat,alt,acc_E,acc_N,acc_h,Q"
    assert lines[1].startswith("DJI_20260906140002_0001_V,9.0000")
    assert ref["acc_N"].min() == 0.03  # raw std 0.003 is floored


@pytest.mark.skipif(shutil.which("exiftool") is None, reason="exiftool not installed")
def test_exif_written_and_read_back(tmp_path, ev):
    from PIL import Image

    make_images(tmp_path, [2, 10, 36])
    img = images.list_images(tmp_path)
    for p in img["path"]:
        Image.new("RGB", (8, 8)).save(p)
    geotag.write_exif(list(img["path"]), ev)
    out = subprocess.run(
        ["exiftool", "-n", "-j", "-GPSLatitude", "-GPSLongitude", "-GPSAltitude", "-XMP-drone-dji:AbsoluteAltitude",
         "-XMP-drone-dji:RtkStdHgt", str(img["path"].iloc[2])],
        capture_output=True, text=True,
    )  # fmt: skip
    tags = json.loads(out.stdout)[0]
    assert tags["GPSLatitude"] == pytest.approx(ev["lat"].iloc[2], abs=1e-8)
    assert tags["GPSAltitude"] == pytest.approx(ev["h"].iloc[2], abs=1e-3)
    assert tags["AbsoluteAltitude"] == pytest.approx(ev["h"].iloc[2], abs=1e-3)
    assert tags["RtkStdHgt"] == pytest.approx(0.008, abs=1e-5)
    assert (tmp_path / (img["name"].iloc[0] + "_original")).exists()  # backup kept by default
    assert np.isfinite(tags["GPSLongitude"])
