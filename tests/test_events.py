import pandas as pd
import pytest

from gnsskit import read_header
from gnsskit.geodesy import enu_diff

from djippk import events, mrk
from djippk.pos import read_trajectory


def test_read_mrk(mrk_file):
    m = mrk.read_mrk(mrk_file)
    assert m["n"].tolist() == [1, 2, 3]
    assert m[["off_n", "off_e", "off_v"]].iloc[0].tolist() == [0.1, 0.05, 0.08]
    assert m["q"].tolist() == [50, 50, 50]
    assert m["gps_s"].iloc[1] - m["gps_s"].iloc[0] == pytest.approx(7.5)


def test_offsets_follow_the_emlid_convention(pos_file, mrk_file):
    pos, m = read_trajectory(pos_file), mrk.read_mrk(mrk_file)
    bare, _ = events.build_events(pos, m, offsets=False)
    shifted, _ = events.build_events(pos, m, offsets=True)
    e, n, u = enu_diff(shifted["lat"], shifted["lon"], shifted["h"], bare["lat"], bare["lon"], bare["h"]).T
    assert (n == pytest.approx(0.1, abs=1e-3)) and (e == pytest.approx(0.05, abs=1e-3)) and (u == pytest.approx(-0.08, abs=1e-3))


def test_written_times_are_rounded_not_truncated(pos_file, mrk_file, tmp_path):
    """Photo 3 is at 35.9996 s after T0: it must print as :36.000, not :35.000."""
    pos, m = read_trajectory(pos_file), mrk.read_mrk(mrk_file)
    ev, skipped = events.build_events(pos, m)
    out = events.write_events(tmp_path / "e.pos", ev, read_header(pos_file), "x")
    last = out.read_text().splitlines()[-1]
    assert last.startswith("2026/09/06 12:00:36.000") and not skipped


def test_events_file_round_trip(pos_file, mrk_file, tmp_path):
    pos, m = read_trajectory(pos_file), mrk.read_mrk(mrk_file)
    ev, _ = events.build_events(pos, m)
    out = events.write_events(tmp_path / "e.pos", ev, read_header(pos_file), "x")
    back = read_trajectory(out)
    assert len(back) == 3
    assert back["gps_s"].to_numpy() == pytest.approx(ev["gps_s"].to_numpy(), abs=1e-3)


def test_photos_outside_the_trajectory_are_reported(pos_file):
    pos = read_trajectory(pos_file)
    m = pd.DataFrame({"n": [1, 2], "gps_s": [pos["gps_s"].iloc[0] + 5, pos["gps_s"].iloc[-1] + 5],
                      "off_n": 0.0, "off_e": 0.0, "off_v": 0.0})  # fmt: skip
    ev, skipped = events.build_events(pos, m)
    assert len(ev) == 1 and skipped == [2]


def test_header_only_pos_gives_a_clear_error(tmp_path):
    p = tmp_path / "empty_events.pos"
    events.write_empty_events(p, ["% program   : x", "%  GPST latitude(deg)"])
    with pytest.raises(ValueError, match="no data lines"):
        read_trajectory(p)
