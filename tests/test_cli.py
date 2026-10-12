from pathlib import Path

import pytest

from djippk import rtklib
from djippk.cli import main
from djippk.rtklib import RtkConfig, build_command, read_base_position


def write_rinex(path: Path, first: str, last: str) -> Path:
    """Minimal RINEX 3 obs file with two epoch lines (only what rinex_span reads)."""
    path.write_text(f"> {first}  0  5\n> {last}  0  5\n")
    return path


def test_config_text_and_base():
    c = RtkConfig().with_base(46.5, 9.5, 2000.0, antenna_h=0.1)
    text = c.to_text()
    assert "pos1-posmode       =kinematic" in text
    assert "ant2-pos1          =46.5000000000" in text and "ant2-antdelu       =0.1000" in text
    assert c.updated({"pos1-navsys": 45}).options["pos1-navsys"] == "45"


def test_build_command_orders_rover_before_base(tmp_path):
    cmd = build_command(Path("c.conf"), Path("r.obs"), Path("b.obs"), [Path("r.nav"), Path("b.nav")], Path("o.pos"))
    assert cmd == ["rnx2rtkp", "-k", "c.conf", "-o", "o.pos", "r.obs", "b.obs", "r.nav", "b.nav"]


def test_read_base_position(tmp_path):
    f = tmp_path / "base.csv"
    f.write_text("latitude(deg),longitude(deg),height(m)\n46.1,9.2,2300.5\n")
    assert read_base_position(f) == (46.1, 9.2, 2300.5)


def test_missing_rnx2rtkp_gives_install_hint(tmp_path):
    with pytest.raises(FileNotFoundError, match="not found on PATH"):
        rtklib.find_rnx2rtkp("definitely-not-rnx2rtkp")


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
    ev = rtklib.read_pos(flight / "DJI_x_001_f_PPKOBS_events.pos")
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
