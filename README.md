# djippk

Post-process the GNSS of **DJI RTK drones** (tested on a Mavic 3 Enterprise) against your own base receiver with
[RTKLIB](https://www.rtklib.com/), and geotag the photos with the result. A command-line replacement for the PPK
and geotagging steps of Emlid Studio.

```
base RINEX ──┐
             ├─ djippk process ─→ <flight>_PPKOBS.pos          trajectory of the antenna (5 Hz)
drone RINEX ─┘                    <flight>_PPKOBS_events.pos   antenna position at every photo, camera offsets applied
drone *.MRK ──────────────────────┘

events + images ─ djippk geotag ─→ <flight>_PPKOBS_metashape.csv   plain-text camera coordinates (default)
                                   GPS tags written into the images    (optional, --exif)
```

Why: the positions DJI stores depend on the coordinates of the base the drone was connected to. If your ground
control or other surveys are tied to a different base, the two differ by a constant shift. Recomputing the
trajectory against the same base removes it.

## Install

Requires Python >= 3.10, RTKLIB's `rnx2rtkp` (build the [demo5 fork](https://github.com/rtklibexplorer/RTKLIB),
developed with `ver.EX 2.5.1`) and, only for `--exif`, [exiftool](https://exiftool.org).

```sh
uv tool install git+https://github.com/franioli/djippk    # or, from a clone: uv sync && uv run djippk --help
uv tool install 'djippk[plots]'                           # + matplotlib for the QC plots
```

## Usage

```sh
# 1. PPK of every flight folder under dji_m3e/, writes the .pos and _events.pos next to the drone RINEX
djippk process dji_m3e/ \
    --base base.26O --base-nav base.26P --base-pos-file base_position.csv --qc

# 2. Match the images to the events and export the coordinates for Metashape
djippk geotag dji_m3e/DJI_x_001/DJI_x_001_PPKOBS_events.pos images/DJI_x_001/

# 2b. ... and also write them into the image EXIF/XMP (exiftool keeps *_original backups)
djippk geotag <events.pos> <images> --exif
```

Flight folders contain `*_PPKOBS.obs`, `*_PPKNAV.nav` and, for the per-photo positions, `*_Timestamp.MRK`.
Without an MRK, `process` writes the trajectory and a header-only events file. The base position is either
`--base-pos LAT LON H` or a CSV (`latitude(deg),longitude(deg),height(m)`, one row); both are in the frame you want
the result in, ellipsoidal heights. Other commands: `djippk events` (events from an existing `.pos`),
`djippk qc` (report and plots). Every command has `--help`.

`geotag` stops before writing anything if the images do not match the events: it checks the number of images
against the number of events, the numbering 1..N and, per photo, the exposure time stored in the image XMP
(falling back to the time between photos in the file names if exiftool is not available).

See [docs/usage.md](docs/usage.md) for what the processing does, every option, the QC, the Metashape import and
troubleshooting.

## Development

```sh
uv sync && uv run pytest
```

The tests use small synthetic flights and a fake `rnx2rtkp`; they need no survey data.
