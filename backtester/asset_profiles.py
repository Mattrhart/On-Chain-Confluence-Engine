"""
asset_profiles.py — per-asset Layer 1 gate routing.

Maps each live symbol to the RibbonParams profile that backtesting showed
works best for that asset (no universal setting).
"""

from __future__ import annotations
from fv_ribbon import RibbonParams

# Profile factories (named for logging / Pine file mapping)
PROFILE_BASELINE = RibbonParams()

PROFILE_SIGMA_ANG_6 = RibbonParams(
    use_sigma_angle=True,
    angle_thresh_deg=6.0,
    angle_directional=False,
)

PROFILE_SIGMA_ANG_DIR = RibbonParams(
    use_sigma_angle=True,
    angle_thresh_deg=10.0,
    angle_directional=True,
)

PROFILE_CHOP_STRONG = RibbonParams(
    req_gap=1.0,
    min_slope=0.06,
)

# yfinance symbol -> (profile label, RibbonParams)
ASSET_PROFILES: dict[str, tuple[str, RibbonParams]] = {
    "ETH-USD":  ("sigma_ang_6",   PROFILE_SIGMA_ANG_6),
    "AUDUSD=X": ("sigma_ang_dir", PROFILE_SIGMA_ANG_DIR),
    "NZDUSD=X": ("sigma_ang_dir", PROFILE_SIGMA_ANG_DIR),
    "USDJPY=X": ("chop_strong",   PROFILE_CHOP_STRONG),
}

DEFAULT_PROFILE = ("baseline", PROFILE_BASELINE)

# Final experiment universe (user's profitable assets)
FINAL_UNIVERSE = ["ETH-USD", "AUDUSD=X", "NZDUSD=X", "USDJPY=X"]


def normalize_symbol(pair: str) -> str:
    return pair.upper().replace("/", "").replace("-", "").replace(" ", "")


def resolve_profile(pair: str) -> tuple[str, RibbonParams]:
    """Return (profile_name, RibbonParams) for a yfinance symbol."""
    key = pair if pair in ASSET_PROFILES else pair.upper()
    if key in ASSET_PROFILES:
        return ASSET_PROFILES[key]
    # fuzzy: ETH-USD vs ETHUSD
    sym = normalize_symbol(pair)
    for k, v in ASSET_PROFILES.items():
        if normalize_symbol(k) == sym:
            return v
    return DEFAULT_PROFILE
