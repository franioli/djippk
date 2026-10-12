"""Quality control of a PPK trajectory, optionally against the DJI positions in the MRK."""

from pathlib import Path

import numpy as np
import pandas as pd

from djippk.geo import enu_diff

Q_NAMES = {1: "fix", 2: "float", 5: "single"}


def pos_summary(pos: pd.DataFrame) -> list[str]:
    """Fix rate, epoch gaps, std of fixed epochs, ratio, satellites and base-age histogram."""
    out = [f"epochs: {len(pos)}   {pos['t'].iloc[0]} -> {pos['t'].iloc[-1]} GPST"]
    for q, c in pos["Q"].value_counts().sort_index().items():
        out.append(f"  Q={q} ({Q_NAMES.get(q, '?')}): {c} ({100 * c / len(pos):.1f}%)")
    dt = np.diff(pos["gps_s"].to_numpy())
    out.append(
        f"rate (median dt): {np.median(dt):.3f} s   max gap: {dt.max():.2f} s   gaps > 1 s: {(dt > 1).sum()}"
    )
    for i in np.where(dt > 1)[0][:10]:
        out.append(f"  gap {dt[i]:.1f} s at {pos['t'].iloc[i]}")
    fix = pos[pos["Q"] == 1]
    if len(fix):
        out.append("fixed-epoch std (m)      median   95%     max")
        for c in ("sdn", "sde", "sdu"):
            p = np.percentile(fix[c], [50, 95, 100])
            out.append(f"  {c}                    {p[0]:.3f}   {p[1]:.3f}   {p[2]:.3f}")
        out.append(
            f"fixed-epoch ratio: median {fix['ratio'].median():.1f}, min {fix['ratio'].min():.1f}"
        )
    out.append(f"satellites: min {pos['ns'].min()}, median {pos['ns'].median():.0f}")
    age = pos["age"].round(1).value_counts().sort_index()
    out.append(
        "base age (s) histogram: " + ", ".join(f"{k:+.1f}:{v}" for k, v in age.items())
    )
    return out


def mrk_compare(pos: pd.DataFrame, mrk: pd.DataFrame) -> tuple[list[str], pd.DataFrame]:
    """PPK minus MRK (DJI) position at each photo, in E/N/U metres; offsets are not removed."""
    t = pos["gps_s"].to_numpy()
    ev = pd.DataFrame({"n": mrk["n"]})
    for c in ("lat", "lon", "h"):
        ev[c] = np.interp(mrk["gps_s"], t, pos[c])
    ev["Q"] = pos["Q"].to_numpy()[
        np.searchsorted(t, mrk["gps_s"]).clip(1, len(pos) - 1)
    ]
    ev[["dE", "dN", "dU"]] = enu_diff(
        ev["lat"], ev["lon"], ev["h"], mrk["lat"], mrk["lon"], mrk["h"]
    )
    out = [
        f"MRK events: {len(ev)}   Q at events: {ev['Q'].value_counts().sort_index().to_dict()}",
        "PPK - MRK (m)   mean     std     min     max   [camera offsets of a few cm not removed]",
    ]
    for c in ("dE", "dN", "dU"):
        out.append(
            f"  {c}           {ev[c].mean():+.3f}  {ev[c].std():.3f}  {ev[c].min():+.3f}  {ev[c].max():+.3f}"
        )
    half = ev.index >= len(ev) // 2
    for c in ("dE", "dN", "dU"):
        out.append(
            f"  {c} 1st half {ev[c][~half].mean():+.3f} / 2nd half {ev[c][half].mean():+.3f}"
        )
    out.append(
        "expected: a roughly constant offset (difference between the two bases) with a std of a few cm; "
        "a drift along the flight or a std above ~5 cm points to a processing problem"
    )
    bad = ev[ev["Q"] != 1]
    if len(bad):
        out.append(
            "non-fixed events (photo n, Q): "
            + ", ".join(f"{n}:{q}" for n, q in zip(bad["n"], bad["Q"]))
        )
    return out, ev


def make_plots(pos: pd.DataFrame, ev: pd.DataFrame | None, stem: Path) -> str:
    """Trajectory coloured by Q, std over time and PPK-MRK per photo; skipped if matplotlib is missing."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return "matplotlib not installed: plots skipped (pip install 'djippk[plots]')"
    first = pos.iloc[[0] * len(pos)]
    enu = enu_diff(
        pos["lat"], pos["lon"], pos["h"], first["lat"], first["lon"], first["h"]
    )
    colors = (
        pos["Q"].map({1: "tab:green", 2: "tab:orange", 5: "tab:red"}).fillna("black")
    )

    fig, ax = plt.subplots(figsize=(7, 7))
    ax.scatter(enu[:, 0], enu[:, 1], c=colors, s=3)
    ax.set(
        xlabel="E (m)",
        ylabel="N (m)",
        title="Trajectory (green=fix, orange=float, red=single)",
        aspect="equal",
    )
    fig.savefig(f"{stem}_traj.png", dpi=130, bbox_inches="tight")
    plt.close(fig)

    t = pos["gps_s"] - pos["gps_s"].iloc[0]
    fig, axs = plt.subplots(3, 1, figsize=(9, 7), sharex=True)
    for ax, c in zip(axs, ("sdn", "sde", "sdu")):
        ax.plot(t, pos[c], lw=0.6)
        ax.set(ylabel=f"{c} (m)", yscale="log")
    axs[-1].set_xlabel("time since start (s)")
    fig.savefig(f"{stem}_std.png", dpi=130, bbox_inches="tight")
    plt.close(fig)

    if ev is not None:
        fig, ax = plt.subplots(figsize=(9, 4))
        for c in ("dE", "dN", "dU"):
            ax.plot(ev["n"], ev[c], ".", label=c)
        ax.set(xlabel="photo number", ylabel="PPK - MRK (m)")
        ax.legend()
        fig.savefig(f"{stem}_vs_mrk.png", dpi=130, bbox_inches="tight")
        plt.close(fig)
    return f"plots written: {stem}_*.png"


def run_qc(
    pos: pd.DataFrame, mrk: pd.DataFrame | None, out_dir: Path, name: str
) -> str:
    """Write `<out_dir>/<name>.txt` (and plots) and return the report text."""
    lines = [f"== {name}"] + pos_summary(pos)
    ev = None
    if mrk is not None:
        mrk_lines, ev = mrk_compare(pos, mrk)
        lines += ["", "== vs MRK (DJI positions)"] + mrk_lines
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / name
    lines += ["", make_plots(pos, ev, stem)]
    text = "\n".join(lines)
    Path(f"{stem}.txt").write_text(text + "\n")
    return text
