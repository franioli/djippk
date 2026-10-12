"""Command line interface: process, events, geotag, qc."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from djippk import __version__, events, geotag, images, qc, rtklib
from djippk.flight import Flight, find_flights
from djippk.mrk import read_mrk


def _key_value(s: str) -> tuple[str, str]:
    if "=" not in s:
        raise argparse.ArgumentTypeError(f"expected KEY=VALUE, got '{s}'")
    k, v = s.split("=", 1)
    return k.strip(), v.strip()


def _rtk_config(
    a: argparse.Namespace, parser: argparse.ArgumentParser
) -> rtklib.RtkConfig:
    config = rtklib.RtkConfig.from_file(a.conf) if a.conf else rtklib.RtkConfig()
    if a.base_pos_file:
        lat, lon, h = rtklib.read_base_position(a.base_pos_file)
    elif a.base_pos:
        lat, lon, h = a.base_pos
    else:
        parser.error(
            "base position missing: use --base-pos LAT LON H or --base-pos-file CSV"
        )
    return config.with_base(lat, lon, h, a.base_ant_h).updated(dict(a.opt))


def _check_coverage(flight: Flight, base_span: tuple) -> str | None:
    """Message if the rover observations are not inside the base time span, else None."""
    start, end = rtklib.rinex_span(flight.obs)
    if start < base_span[0] or end > base_span[1]:
        return f"rover {start} - {end} GPST is not inside the base {base_span[0]} - {base_span[1]}"
    return None


def process_flight(
    flight: Flight,
    base: Path,
    base_nav: Sequence[Path],
    config: rtklib.RtkConfig,
    exe: str,
    do_qc: bool,
) -> str:
    """PPK of one flight, then its events file; returns a one-line summary."""
    pos_path = Path(f"{flight.stem}.pos")
    config.write(Path(f"{flight.stem}.conf"))
    rtklib.run_rnx2rtkp(flight.obs, base, [flight.nav, *base_nav], config, pos_path, exe)
    pos = rtklib.read_pos(pos_path)
    q = pos["Q"].value_counts(normalize=True).mul(100).round(1).to_dict()
    msg = f"{pos_path.name}: {len(pos)} epochs, Q%={q}"
    events_path = Path(f"{flight.stem}_events.pos")
    mrk = read_mrk(flight.mrk) if flight.mrk else None
    if mrk is None:
        events.write_empty_events(events_path, rtklib.read_header(pos_path))
        msg += "; no MRK: empty events file"
    else:
        ev, skipped = events.build_events(pos, mrk)
        events.write_events(
            events_path, ev, rtklib.read_header(pos_path), pos_path.name
        )
        nonfix = ev.loc[ev["Q"] != 1, "n"].tolist()
        msg += f"; {len(ev)} events"
        if skipped:
            msg += f", WARNING photos outside the trajectory: {skipped}"
        if nonfix:
            msg += f", non-fixed photos: {nonfix}"
    if do_qc:
        qc.run_qc(pos, mrk, flight.obs.parent / "qc", pos_path.stem)
    return msg


def cmd_process(a: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    config = _rtk_config(a, parser)
    flights = find_flights(a.paths)
    base_span = rtklib.rinex_span(a.base)
    failed = 0
    for fl in flights:
        print(f"== {fl.obs.name}")
        try:
            problem = _check_coverage(fl, base_span)
            if problem:
                raise RuntimeError(problem)
            print("  " + process_flight(fl, a.base, a.base_nav, config, a.exe, a.qc))
        except (RuntimeError, ValueError, FileNotFoundError) as e:
            print(f"  FAILED: {e}", file=sys.stderr)
            failed += 1
    return 1 if failed else 0


def cmd_events(a: argparse.Namespace, _: argparse.ArgumentParser) -> int:
    pos = rtklib.read_pos(a.pos)
    ev, skipped = events.build_events(pos, read_mrk(a.mrk), offsets=not a.no_offsets)
    out = a.out or Path(a.pos).with_name(Path(a.pos).stem + "_events.pos")
    events.write_events(out, ev, rtklib.read_header(a.pos), Path(a.pos).name)
    print(f"{len(ev)} events written to {out}")
    if skipped:
        print(f"warning: photos outside the trajectory, skipped: {skipped}")
    return 0


def cmd_geotag(a: argparse.Namespace, _: argparse.ArgumentParser) -> int:
    ev = rtklib.read_pos(a.events)
    img = images.list_images(a.images, a.suffix)
    exposure = images.exposure_times(list(img["path"])) if len(img) else None
    problems = images.check_match(img, ev, exposure)
    if problems:
        print("images and events do not match:", file=sys.stderr)
        for p in problems:
            print("  -", p, file=sys.stderr)
        return 1
    how = (
        "XMP exposure time"
        if exposure is not None
        else "file-name intervals (no XMP exposure time)"
    )
    ref = geotag.build_reference(img, ev, a.min_acc, a.keep_ext)
    out = a.out or Path(a.images) / (
        Path(a.events).stem.removesuffix("_events") + "_metashape.csv"
    )
    geotag.write_reference(ref, out)
    print(f"{len(ref)} images matched by {how}\nwritten: {out}")
    nonfix = ref[ref["Q"] != 1]
    if len(nonfix):
        print(
            f"non-fixed photos ({len(nonfix)}): "
            + ", ".join(
                f"{label}:Q{q}" for label, q in zip(nonfix["label"], nonfix["Q"])
            )
        )
    if a.exif:
        geotag.write_exif(list(img["path"]), ev, backup=not a.no_backup)
        print(
            f"GPS tags written into {len(img)} images"
            + ("" if a.no_backup else " (originals kept as *_original)")
        )
    return 0


def cmd_qc(a: argparse.Namespace, _: argparse.ArgumentParser) -> int:
    pos = rtklib.read_pos(a.pos)
    print(qc.run_qc(pos, read_mrk(a.mrk) if a.mrk else None, a.out, Path(a.pos).stem))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="djippk", description=__doc__)
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser(
        "process",
        help="PPK of flight folders against a base, writes .pos and _events.pos",
    )
    sp.add_argument(
        "paths",
        type=Path,
        nargs="+",
        help="flight folders (searched recursively) or *_PPKOBS.obs files",
    )
    sp.add_argument(
        "--base", type=Path, required=True, help="base RINEX observation file"
    )
    sp.add_argument(
        "--base-nav",
        type=Path,
        nargs="+",
        required=True,
        help="base RINEX navigation file(s), e.g. GPS .26P plus BeiDou .26B",
    )
    sp.add_argument(
        "--base-pos",
        type=float,
        nargs=3,
        metavar=("LAT", "LON", "H"),
        help="base position (deg, deg, ellipsoidal m)",
    )
    sp.add_argument(
        "--base-pos-file", type=Path, help="CSV with header and one row: lat, lon, h"
    )
    sp.add_argument(
        "--base-ant-h",
        type=float,
        default=0.0,
        help="base antenna height above the base position [m] (default 0)",
    )
    sp.add_argument(
        "--conf", type=Path, help="RTKLIB .conf loaded on top of the built-in defaults"
    )
    sp.add_argument(
        "--opt",
        type=_key_value,
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="RTKLIB option override, repeatable",
    )
    sp.add_argument(
        "--qc",
        action="store_true",
        help="also write the QC report and plots to <flight>/qc",
    )
    sp.add_argument("--exe", default="rnx2rtkp", help="rnx2rtkp executable")
    sp.set_defaults(func=cmd_process)

    sp = sub.add_parser(
        "events", help="build the _events.pos from an existing .pos and an MRK"
    )
    sp.add_argument("pos", type=Path)
    sp.add_argument("mrk", type=Path)
    sp.add_argument("-o", "--out", type=Path)
    sp.add_argument(
        "--no-offsets", action="store_true", help="do not apply the MRK camera offsets"
    )
    sp.set_defaults(func=cmd_events)

    sp = sub.add_parser(
        "geotag",
        help="match images to events; write a Metashape reference file, optionally the EXIF tags",
    )
    sp.add_argument("events", type=Path, help="*_events.pos")
    sp.add_argument("images", type=Path, help="folder with the DJI images")
    sp.add_argument(
        "-o",
        "--out",
        type=Path,
        help="reference file (default <images>/<flight>_PPKOBS_metashape.csv)",
    )
    sp.add_argument(
        "--exif",
        action="store_true",
        help="also write the coordinates into the image EXIF/XMP (needs exiftool)",
    )
    sp.add_argument(
        "--no-backup",
        action="store_true",
        help="with --exif: do not keep *_original copies",
    )
    sp.add_argument(
        "--suffix", default="V", help="image type letter in the file name (default V)"
    )
    sp.add_argument(
        "--min-acc",
        type=float,
        default=0.03,
        help="floor for the accuracies [m] (default 0.03)",
    )
    sp.add_argument(
        "--keep-ext", action="store_true", help="keep the file extension in the label"
    )
    sp.set_defaults(func=cmd_geotag)

    sp = sub.add_parser(
        "qc", help="quality report (and plots) of a .pos, optionally against an MRK"
    )
    sp.add_argument("pos", type=Path)
    sp.add_argument("mrk", type=Path, nargs="?")
    sp.add_argument("--out", type=Path, default=Path("qc"))
    sp.set_defaults(func=cmd_qc)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    a = parser.parse_args(argv)
    try:
        return a.func(a, parser)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
