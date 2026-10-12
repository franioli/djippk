"""Locate the files of a DJI flight folder."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Flight:
    """Files of one flight; `mrk` is None if the folder has no `*_Timestamp.MRK`."""

    obs: Path
    nav: Path
    mrk: Path | None

    @property
    def stem(self) -> Path:
        """Output prefix next to the rover RINEX: `<flight>_PPKOBS`."""
        return self.obs.with_suffix("")


def find_flights(paths: list[Path]) -> list[Flight]:
    """Flights found under the given folders (searched recursively) or given directly as `*_PPKOBS.obs` files.

    Each flight needs a `*_PPKNAV.nav` beside its observations; the MRK is optional.
    """
    obs_files: list[Path] = []
    for p in paths:
        obs_files += [p] if p.is_file() else sorted(p.rglob("*_PPKOBS.obs"))
    if not obs_files:
        raise FileNotFoundError("no *_PPKOBS.obs found in the given paths")
    flights = []
    for obs in obs_files:
        prefix = obs.name.removesuffix("_PPKOBS.obs")
        nav = obs.with_name(f"{prefix}_PPKNAV.nav")
        if not nav.exists():
            raise FileNotFoundError(f"missing navigation file {nav}")
        mrk = obs.with_name(f"{prefix}_Timestamp.MRK")
        flights.append(Flight(obs, nav, mrk if mrk.exists() else None))
    return flights
