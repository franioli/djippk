from pathlib import Path


from gnsskit import RtkConfig

from djippk.cli import main
from djippk.config import DEFAULT_CONFIG, read_base_position
from djippk.pos import read_trajectory


def write_rinex(path: Path, first: str, last: str) -> Path:
    """Minimal RINEX 3 obs file with two epoch lines (only what rinex_span reads)."""
    path.write_text(f"> {first}  0  5\n> {last}  0  5\n")
    return path


def test_default_config_and_base():
    c = DEFAULT_CONFIG.with_base_llh(46.5, 9.5, 2000.0, antenna_h=0.1)
    o = c.options
    assert o["pos1-posmode"] == "kinematic" and o["pos1-navsys"] == "41" and o["misc-timeinterp"] == "on"
    assert o["ant2-postype"] == "llh" and o["ant2-pos1"] == "46.5" and o["ant2-antdelu"] == "0.1"
    assert "pos1-posopt1" not in o  # only the options of the defaults are written


def test_conf_file_gives_way_to_base_position_and_opt(tmp_path):
    conf = tmp_path / "user.conf"
    conf.write_text("pos1-elmask=10\nant2-pos1=1\nant2-pos2=2\nant2-pos3=3\n")
    o = RtkConfig.from_file(conf, DEFAULT_CONFIG).with_base_llh(46.0, 9.0, 2000.0).options
    assert o["pos1-elmask"] == "10" and o["ant2-pos1"] == "46.0" and o["ant2-pos3"] == "2000.0"


def test_read_base_position(tmp_path):
    f = tmp_path / "base.csv"
    f.write_text("latitude(deg),longitude(deg),height(m)\n46.1,9.2,2300.5\n")
    assert read_base_position(f) == (46.1, 9.2, 2300.5)


def test_missing_rnx2rtkp_is_reported(tmp_path, capsys):
    args = ["qc", "none.pos"]
    assert main(args) == 1 and "error:" in capsys.readouterr().err


def test_process_end_to_end(tmp_path, pos_file, mrk_file, fake_rnx2rtkp, capsys):
    flight = tmp_path / "DJI_x_001_f"
    flight.mkdir()
    write_rinex(flight / "DJI_x_001_f_PPKOBS.obs", "2026 09 06 12 00  1.0000000", "2026 09 06 12 00 50.0000000")
    (flight / "DJI_x_001_f_PPKNAV.nav").write_text("")
    (flight / "DJI_x_001_f_Timestamp.MRK").write_text(mrk_file.read_text())
    base = write_rinex(tmp_path / "base.26O", "2026 09 06 11 00  0.0000000", "2026 09 06 13 00  0.0000000")
    nav = tmp_path / "base.26P"
    nav.write_text("")
    args = ["process", str(flight), "--base", str(base), "--base-nav", str(nav), "--base-pos", "46.0", "9.0", "2000.0",
            "--exe", fake_rnx2rtkp, "--qc"]  # fmt: skip
    assert main(args) == 0
    assert (flight / "DJI_x_001_f_PPKOBS.pos").exists() and (flight / "DJI_x_001_f_PPKOBS.conf").exists()
    ev = read_trajectory(flight / "DJI_x_001_f_PPKOBS_events.pos")
    assert len(ev) == 3
    assert (flight / "qc" / "DJI_x_001_f_PPKOBS.txt").exists()
    assert "3 events" in capsys.readouterr().out


def test_process_without_mrk_writes_empty_events_and_flags_uncovered_flights(tmp_path, fake_rnx2rtkp, capsys):
    flight = tmp_path / "f"
    flight.mkdir()
    write_rinex(flight / "a_PPKOBS.obs", "2026 09 06 12 00  1.0000000", "2026 09 06 12 00 50.0000000")
    (flight / "a_PPKNAV.nav").write_text("")
    nav = tmp_path / "b.nav"
    nav.write_text("")
    base = write_rinex(tmp_path / "base.26O", "2026 09 06 11 00  0.0000000", "2026 09 06 13 00  0.0000000")
    ok = ["process", str(flight), "--base", str(base), "--base-nav", str(nav), "--base-pos", "46", "9", "2000",
          "--exe", fake_rnx2rtkp]  # fmt: skip
    assert main(ok) == 0
    assert "no MRK" in capsys.readouterr().out
    assert not [ln for ln in (flight / "a_PPKOBS_events.pos").read_text().splitlines() if not ln.startswith("%")]
    late = write_rinex(tmp_path / "late.26O", "2026 09 06 12 30  0.0000000", "2026 09 06 13 00  0.0000000")
    assert main(["process", str(flight), "--base", str(late), *ok[4:]]) == 1  # base starts after the flight
    assert "not inside the base" in capsys.readouterr().err


def test_several_base_nav_files_are_all_passed_on(tmp_path, capsys):
    from djippk.cli import build_parser

    a = build_parser().parse_args(
        ["process", "dir", "--base", "b.obs", "--base-nav", "b.26P", "b.26B", "--base-pos", "46", "9", "2000"]
    )
    assert [str(p) for p in a.base_nav] == ["b.26P", "b.26B"] and [str(p) for p in a.paths] == ["dir"]
