"""
sigma_angle.py — Yang-Zhang volatility + ICS trend angle (ported from ST-EP06).

The idea we're stealing: instead of the crude `min_slope` chop filter, measure the
trend in a VOLATILITY-NORMALIZED coordinate system. Yang-Zhang (2000) gives a
drift-independent per-bar sigma from full OHLC; dividing log-price slope by sigma
yields a dimensionless "sigma-per-bar" slope whose arctan is a degrees angle that
is comparable across ETH, JPY, AUD, regimes, and timeframes.

Chop filter: |angle| < range_threshold  =>  ranging (suppress signals).
Trend angle is the principled replacement for `min_slope`.
"""

from __future__ import annotations
import numpy as np
import pandas as pd

MIN_SIGMA = 1e-10


def yang_zhang_sigma(df: pd.DataFrame, length: int = 20) -> pd.Series:
    """
    Drift-independent realized volatility per bar (Yang & Zhang, 2000).
        sigma^2 = var(overnight) + k*var(open->close) + (1-k)*Rogers-Satchell
    Uses population variance (ddof=0) to match Pine's ta.variance.
    """
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    prev_c = c.shift(1).fillna(o)

    yz_or = np.log(o / prev_c)            # overnight gap
    yz_co = np.log(c / o)                 # open -> close
    yz_ho = np.log(h / o)
    yz_hc = np.log(h / c)
    yz_lo = np.log(l / o)
    yz_lc = np.log(l / c)

    sq_or = yz_or.rolling(length).var(ddof=0)
    sq_co = yz_co.rolling(length).var(ddof=0)
    sq_rs = (yz_ho * yz_hc + yz_lo * yz_lc).rolling(length).mean()

    k = 0.34 / (1.34 + (length + 1.0) / max(length - 1.0, 1.0))
    sq = sq_or.fillna(0) + k * sq_co.fillna(0) + (1.0 - k) * sq_rs.fillna(0)
    sigma = np.sqrt(sq.clip(lower=0.0)).clip(lower=MIN_SIGMA)
    return sigma


def ics_trend_angle(price: pd.Series, sigma: pd.Series, lookback: int = 13) -> pd.Series:
    """
    ICS angle in degrees: arctan( (sigma-per-bar log slope) ) * 180/pi.
    +45deg ~ price rising at 1 sigma/bar. Sign = trend direction, |value| = strength.
    """
    log_p = np.log(price.clip(lower=MIN_SIGMA))
    slope_per_bar = (log_p - log_p.shift(lookback)) / lookback
    norm_slope = slope_per_bar / sigma.clip(lower=MIN_SIGMA)
    angle = np.degrees(np.arctan(norm_slope))
    return angle
