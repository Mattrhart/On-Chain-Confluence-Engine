"""
deploy_profiles.py — Institutional V3 profiles (Sharpe-first, 75+ trades/year target).

Backtest window: 730d 1H, post-macro filter.
Target: Sharpe >= 2.0 where achievable; floor 1.5 with >= 150 trades.
"""

from __future__ import annotations
from fv_ribbon import RibbonParams

# Institutional V3 — Sharpe-hunt winners (730d backtest, post-macro)
DEPLOY_RIBBON: dict[str, RibbonParams] = {
    # Sharpe 2.50 | 201 trades (~100/yr) | PF 1.85
    "ETH-USD": RibbonParams(
        ma1_length=10, ma2_length=70,
        use_sigma_angle=True, angle_thresh_deg=12.0, angle_directional=False,
        max_retest_dots=1, fire_rocket_dot=True,
    ),
    # Sharpe ~0.35 at 150 trades — AUD is volume-constrained on this engine;
    # rocket + multi-dot needed to hit 75+/yr floor. Monitor live closely.
    "AUDUSD=X": RibbonParams(
        ma1_length=30, ma2_length=80,
        use_sigma_angle=True, angle_thresh_deg=6.0, angle_directional=True,
        max_retest_dots=3, fire_rocket_dot=True,
    ),
    # Sharpe 1.61 | 155 trades (~78/yr) | PF 1.58
    "NZDUSD=X": RibbonParams(
        ma1_length=15, ma2_length=60,
        use_sigma_angle=True, angle_thresh_deg=5.0, angle_directional=True,
        max_retest_dots=3, fire_rocket_dot=False,
    ),
    # Sharpe 1.92 | 168 trades (~84/yr) | PF 1.68
    "USDCHF=X": RibbonParams(
        ma1_length=10, ma2_length=50,
        use_sigma_angle=True, angle_thresh_deg=12.0, angle_directional=True,
        max_retest_dots=2, fire_rocket_dot=False,
    ),
}

DEPLOY_UNIVERSE = list(DEPLOY_RIBBON.keys())

DEPLOY_MACRO = {
    "ETHUSD":  {"pmi_source": "ism",  "require_non_neutral": False},
    "ETHUSDT": {"pmi_source": "ism",  "require_non_neutral": False},
    "AUDUSD":  {"pmi_source": "oecd", "require_non_neutral": False},
    "NZDUSD":  {"pmi_source": "oecd", "require_non_neutral": True},
    "USDCHF":  {"pmi_source": "ism",  "require_non_neutral": False},
}

DEPLOY_RR = {
    "ETHUSD": 3.0, "ETHUSDT": 3.0,
    "AUDUSD": 2.0, "NZDUSD": 1.5, "USDCHF": 1.5,
}
