# djippk usage guide

## 1. What the processing does

The drone logs raw GNSS observations (code and carrier phase) at 5 Hz; the base logs the same at a known point,
typically at 1 Hz. RTKLIB forms double differences between rover and base, which removes satellite and receiver
clock errors and most of the atmospheric delay on a short baseline, resolves the carrier-phase integer ambiguities
and returns the rover position relative to the base. The filter runs forward and backward (`pos1-soltype=combined`),
so an epoch before the ambiguities were fixed still benefits from the fix reached later.

- **Quality flag Q.** The solution is *fixed* (Q=1, cm level) if the ratio between the best and second-best integer
  candidates exceeds `pos2-arthres` (3.0); otherwise *float* (Q=2, dm level), or *single* (Q=5, metres).
- **The base position defines the result.** Rover coordinates are the base coordinates plus the baseline, so the
  trajectory is in the frame and height type of the base position you give. Use a properly determined position,
  never the approximate one in the RINEX header.
- **Base antenna height.** The base position must refer to the same point as the antenna height you give
  (`--base-ant-h`, default 0 = the position is that of the antenna). A wrong value shifts the whole trajectory
  vertically by the error. This is the most common cause of a constant height offset between two PPK solutions:
  an offset of ~1.2 m between two bases that agree horizontally to 2 cm was, in the test survey, an antenna height
  entered as 1.8 m instead of ~0.6 m.
- **Time.** All times are GPS time. `rnx2rtkp` writes GPST; the MRK holds GPS week and time of week; the image XMP
  tag `UTCAtExposure` is named UTC but contains GPS time (it equals the MRK time to the microsecond). File names
  carry the camera clock, which can be off by seconds, so they are used only as a fallback.
- **Camera position.** The `.pos` is the trajectory of the GNSS antenna. The MRK lists the antenna-to-camera offsets
  (N, E, V in mm). The events file applies them like Emlid Studio does: N added to the northing, E to the easting,
  V *subtracted* from the ellipsoidal height (verified against Emlid Studio output to 3 mm).
- **Base interpolation.** `misc-timeinterp=on` asks RTKLIB to interpolate the 1 Hz base to the rover epochs. The
  `age` column of the `.pos` (shown as a histogram in the QC) keeps the spread of nearest-epoch matching either way,
  so it does not tell whether interpolation is active. The solution is at the rover rate in both cases.

## 2. Files

```
<flight folder>/
    <flight>_PPKOBS.obs  <flight>_PPKNAV.nav  <flight>_Timestamp.MRK     from the drone
    <flight>_PPKOBS.pos           trajectory (llh, GPST, ellipsoidal height)
    <flight>_PPKOBS.conf          the RTKLIB settings actually used (reproducibility)
    <flight>_PPKOBS_events.pos    one line per photo, shooting order, camera offsets applied
    qc/                           with --qc: text report and plots
```

The `_events.pos` has the layout Emlid Studio writes, so tools that read those files accept it. Line N is photo N.
`rnx2rtkp` also writes an (empty) `_events.pos` itself because the DJI RINEX contains no shutter events;
`djippk process` replaces it.

## 3. Commands

### `djippk process PATH... --base OBS --base-nav NAV (--base-pos LAT LON H | --base-pos-file CSV)`

`PATH` are flight folders (searched recursively for `*_PPKOBS.obs`) or `.obs` files. For each flight it checks that
the rover observations lie inside the time span of the base, runs `rnx2rtkp`, writes `.pos`, `.conf` and
`_events.pos` and prints the fix percentages and the photos that are not fixed or lie outside the trajectory.
A failing flight is reported and the others continue; the exit code is 1 if any failed.

| Option | Meaning |
|---|---|
| `--base-ant-h H` | base antenna height above the base position [m], default 0 |
| `--conf FILE` | RTKLIB `.conf` applied on top of the built-in defaults |
| `--opt KEY=VALUE` | override one RTKLIB option, repeatable, e.g. `--opt pos1-navsys=45 --opt pos2-gloarmode=on` |
| `--qc` | also write `qc/` per flight |
| `--exe PATH` | `rnx2rtkp` executable if not on the `PATH` |

Built-in settings: kinematic, forward + backward, L1+L2, elevation mask 15 deg, GPS + Galileo + BeiDou
(`navsys=41`; add 4 for GLONASS, 16 for QZSS), continuous ambiguity resolution with GLONASS AR off, broadcast
ionosphere and orbits, Saastamoinen troposphere, no dynamics model. They are written in full to `<flight>_PPKOBS.conf`.

### `djippk events POS MRK [-o OUT] [--no-offsets]`

Rebuilds the events file from an existing `.pos`, e.g. after editing the `.pos` or to get the bare antenna positions
(`--no-offsets`). Positions are linearly interpolated at the exposure times; Q is the worse of the two neighbouring
epochs, so a photo between a fixed and a float epoch is marked float.

### `djippk geotag EVENTS IMAGES [-o OUT] [--exif] [--no-backup] [--suffix V] [--min-acc 0.03] [--keep-ext]`

Matches `DJI_<time>_<NNNN>_V.JPG` images to the events (image N to event N), after checking:

1. one image per number, numbers 1..N, and as many images as events;
2. each image's XMP exposure time equals its event time within 10 ms; without exiftool or XMP, the intervals between
   consecutive photos in the file names equal those of the events within 1.5 s.

It then writes `<IMAGES>/<flight>_PPKOBS_metashape.csv` with columns `label,lon,lat,alt,acc_E,acc_N,acc_h,Q`
(geographic degrees, ellipsoidal metres; the accuracies are the solution std floored at `--min-acc`).

`--exif` additionally writes, with one exiftool run, the EXIF GPS latitude, longitude and altitude and the DJI XMP
`GPSLatitude`, `GPSLongitude`, `AbsoluteAltitude`, `RtkStdLat`, `RtkStdLon`, `RtkStdHgt` (the tags Emlid Studio
writes). exiftool keeps `<image>_original` copies unless `--no-backup`. `RtkFlag` and everything else is left as is.
Writing positions into the images is irreversible without those backups.

### `djippk qc POS [MRK] [--out DIR]`

Fix rate, epoch gaps, std of the fixed epochs, ratio, satellite count, and with an MRK the PPK-minus-MRK
difference in E/N/U per flight, plus plots if matplotlib is installed.

## 4. Reading the QC

- **Fix rate:** aim for more than 95% fixed. Non-fixed photo numbers are listed.
- **Gaps:** the spacing should equal the rover rate (0.2 s at 5 Hz); gaps over 1 s are listed.
- **Fixed std:** millimetres in N/E and about a centimetre in U at the median on a short baseline.
- **PPK minus MRK:** the MRK holds the DJI (base-dependent) positions, so a *constant* offset per flight is the
  expected difference between the two bases. A drift along the flight or a std above a few cm points to a
  processing problem. The camera offsets are not removed in this comparison.

## 5. Metashape

- **Text file:** Reference pane > Import Reference, delimiter comma, map the columns to label, longitude, latitude,
  altitude and accuracies (ignore Q). Choose the geographic coordinate system of the frame of your base
  coordinates, e.g. ETRF2000-RDN2008.
- **EXIF route:** Metashape reads EXIF GPS as WGS84. To keep the positions in the frame of your base, set the camera
  coordinate system to that frame instead of letting Metashape convert it (unverified here: check one camera).
- Use the ground control points as check points first, optimise the camera model, and read the check-point errors:
  a few cm means the old residuals came from the base; a constant offset points to the GCP or base coordinates;
  a variable error to calibration, strip geometry or lever arm.

## 6. Troubleshooting

- **`rnx2rtkp not found`:** install RTKLIB or pass `--exe`.
- **`not inside the base`:** the base log must cover the whole flight; check the time spans (GPST).
- **No fixed solutions:** wrong base position or antenna height, too few common constellations or frequencies
  between rover and base (compare the `SYS / # / OBS TYPES` lines of the two RINEX headers).
- **Low fix rate on one flight:** try `--opt pos1-navsys=45 --opt pos2-gloarmode=on`, `--opt pos2-armode=fix-and-hold`,
  `--opt pos1-ionoopt=off`, or `--opt pos1-frequency=l1` (useful when rover and base track different signals on L2).
- **`N images but M events`:** photos outside the trajectory are skipped by `process`/`events` and reported;
  images from a different flight, or a second copy (JPG and DNG), also trigger this.
- **`has no data lines`:** the first argument was an empty events file; give the trajectory `.pos`.

## 7. Not verified

- The base interpolation (section 1), and whether a given RTKLIB build accepts every key; option names differ
  between versions.
- That `AbsoluteAltitude`/`GPSAltitude` are read as ellipsoidal heights by every downstream tool.
- The meaning of the MRK quality flag (50 appears for RTK fixed) and of the camera-offset signs beyond the match
  with Emlid Studio.
