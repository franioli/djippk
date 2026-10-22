"""Default RTKLIB configuration for kinematic PPK of a drone."""

from gnsskit import RtkConfig

# Kinematic, dual-frequency, short-baseline (GPS+Galileo+BeiDou, GLONASS AR off), forward+backward.
# Built from `empty()` so that only the options below are written to the .conf file.
DEFAULT_CONFIG = RtkConfig.empty().updated(
    posmode="kinematic",
    frequency="l1+l2",
    soltype="combined",
    elmask=15.0,
    snrmask_r=False,
    snrmask_b=False,
    dynamics=False,
    ionoopt="brdc",
    tropopt="saas",
    sateph="brdc",
    navsys="GEC",
    armode="continuous",
    gloarmode="off",
    bdsarmode=True,
    arthres=3.0,
    arlockcnt=0,
    arelmask=15.0,
    timeinterp=True,
    rover_postype="llh",
    rover_anttype="",
    base_anttype="",
    base_antdel=(0.0, 0.0, 0.0),
    solformat="llh",
    outhead=True,
    outopt=True,
    timesys="gpst",
    timeform="hms",
    timendec=3,
    degform="deg",
    height="ellipsoidal",
    geoid="internal",
)
