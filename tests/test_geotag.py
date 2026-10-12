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
    assert lines[1].startswith("DJI_20260906140002_0001_V.JPG,9.0000")
    stem = geotag.build_reference(img, ev, keep_ext=False)
    assert stem["label"].iloc[0] == "DJI_20260906140002_0001_V"
    assert ref["acc_N"].min() == 0.03  # raw std 0.003 is floored


def read_tags(path: Path) -> dict:
    out = subprocess.run(
        ["exiftool", "-n", "-j", "-GPSLatitude", "-GPSAltitude", "-XMP-drone-dji:AbsoluteAltitude", "-XMP-drone-dji:RtkStdHgt", str(path)],
        capture_output=True, text=True,
    )  # fmt: skip
    return json.loads(out.stdout)[0]


@pytest.fixture
def jpeg_folder(tmp_path):
    from PIL import Image

    folder = tmp_path / "imgs"
    folder.mkdir()
    make_images(folder, [2, 10, 36])
    img = images.list_images(folder)
    for p in img["path"]:
        Image.new("RGB", (8, 8)).save(p)
    return img


@pytest.mark.skipif(shutil.which("exiftool") is None, reason="exiftool not installed")
def test_exif_goes_to_copies_by_default(jpeg_folder, ev, tmp_path):
    img, out = jpeg_folder, tmp_path / "tagged"
    done = geotag.write_exif(list(img["path"]), ev, out)
    assert [p.name for p in done] == img["name"].tolist()
    tags = read_tags(out / img["name"].iloc[2])
    assert tags["GPSLatitude"] == pytest.approx(ev["lat"].iloc[2], abs=1e-8)
    assert tags["GPSAltitude"] == pytest.approx(ev["h"].iloc[2], abs=1e-3)
    assert tags["AbsoluteAltitude"] == pytest.approx(ev["h"].iloc[2], abs=1e-3)
    assert tags["RtkStdHgt"] == pytest.approx(0.008, abs=1e-5)
    assert "GPSLatitude" not in read_tags(img["path"].iloc[2])  # the input image is untouched
    assert not list(out.glob("*_original")) and not list(img["path"].iloc[0].parent.glob("*_original"))


@pytest.mark.skipif(shutil.which("exiftool") is None, reason="exiftool not installed")
def test_exif_in_place_only_when_asked_and_without_backups(jpeg_folder, ev):
    img = jpeg_folder
    geotag.write_exif(list(img["path"]), ev, None)
    assert read_tags(img["path"].iloc[0])["GPSLatitude"] == pytest.approx(ev["lat"].iloc[0], abs=1e-8)
    assert not list(img["path"].iloc[0].parent.glob("*_original"))
    with pytest.raises(ValueError, match="is the image folder"):
        geotag.write_exif(list(img["path"]), ev, img["path"].iloc[0].parent)
