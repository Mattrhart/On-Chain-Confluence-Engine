"""
deploy_profiles.py — Institutional V4 profiles (15m-validated, live chart TF).

Backtest window: 60d 15m (yfinance max intraday), post-macro filter.
Bar counts match Pine scripts on 15m charts exactly.
AUD V4: tight ribbon + Donchian structure breakout (quality over quantity).
"""

from __future__ import annotations
from fv_ribbon import RibbonParams

# Institutional V4 — 15m-validated (60d yfinance, post-macro)
DEPLOY_RIBBON: dict[str, RibbonParams] = {
    # 15m: Sharpe 2.71 | 50 trades/60d | PF 1.44
    "ETH-USD": RibbonParams(
        ma1_length=10, ma2_length=70,
        use_sigma_angle=True, angle_thresh_deg=12.0, angle_directional=False,
        max_retest_dots=1, fire_rocket_dot=True,
    ),
    # V4: σ≥12° 1 dot + Donchian breakout — KEEP (quality over quantity)
    # 15m: Sharpe 1.75 | 33 trades/60d | PF 1.34
    "AUDUSD=X": RibbonParams(
        ma1_length=30, ma2_length=80,
        use_sigma_angle=True, angle_thresh_deg=12.0, angle_directional=True,
        max_retest_dots=1, fire_rocket_dot=False,
        use_structure_breakout=True, breakout_lookback=16,
        breakout_atr_mult=1.4, max_breakout_dots=1,
    ),
    # 15m: Sharpe 2.87 | 66 trades/60d | PF 1.47 (require_non_neutral=True)
    "NZDUSD=X": RibbonParams(
        ma1_length=15, ma2_length=60,
        use_sigma_angle=True, angle_thresh_deg=12.0, angle_directional=True,
        max_retest_dots=3, fire_rocket_dot=True,
    ),
    # 15m: Sharpe 2.44 | 55 trades/60d | PF 1.40
    "USDCHF=X": RibbonParams(
        ma1_length=10, ma2_length=50,
        use_sigma_angle=True, angle_thresh_deg=6.0, angle_directional=True,
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
    "AUDUSD": 1.5, "NZDUSD": 3.0, "USDCHF": 1.5,
}

# Live chart timeframe — all profiles validated on this interval
DEPLOY_INTERVAL = "15m"
DEPLOY_PERIOD = "60d"
