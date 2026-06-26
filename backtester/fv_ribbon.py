"""
fv_ribbon.py — Python port of "FV Ribbon [Apex Ignite V26] - Hardened" (Layer 1).

This reproduces the Pine logic 1:1, including the stateful latch (var bool
bull_ignited / bear_ignited) and the single "first strike" retest dot per arm.

Input  : DataFrame with open/high/low/close + ema20_4h/ema50_4h (from data_providers.attach_htf_shield)
Output : same frame plus signal columns:
         bull_ignited, bear_ignited, bull_dot, bear_dot, risk_atr
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass

from sigma_angle import yang_zhang_sigma, ics_trend_angle


@dataclass
class RibbonParams:
    ma1_length: int = 20       # Fast EMA
    ma2_length: int = 50       # Slow SMA
    prox_input: float = 0.25   # Early Crossover Proximity (%)
    min_slope: float = 0.03    # Min 50 SMA slope (%) — chop killer
    thrust_lookback: int = 3   # Price thrust lookback (bars)
    thrust_req: float = 1.5    # Vertical price thrust requirement (ATR)
    req_gap: float = 0.5       # Required gap (macro ATR)
    ct_max_bars: int = 16      # Counter-trend max duration (bars)
    macro_atr_len: int = 100   # ATR used for gap/thrust normalisation
    risk_atr_len: int = 14     # ATR used by the risk model (stops)
    require_htf_align: bool = False  # EXPERIMENT: only take dots aligned with the 4H shield
    # --- Yang-Zhang sigma-angle chop gate (ST-EP06 port) ---
    use_sigma_angle: bool = False    # replace crude min_slope chop killer with sigma-angle
    yz_sigma_len: int = 20           # Yang-Zhang volatility lookback
    angle_lookback: int = 13         # bars for the ICS trend-angle slope
    angle_thresh_deg: float = 8.0    # |angle| below this => ranging (suppress dots)
    angle_directional: bool = False  # also require angle sign to match trade direction
    # --- Expansion capture (catch moves beyond first retest) ---
    max_retest_dots: int = 1         # max entry dots per ribbon arm (1 = legacy first-strike only)
    fire_rocket_dot: bool = False    # also fire on vertical thrust bar (rocket override)
    # --- Structure breakout edge (non-ribbon expansion capture) ---
    use_structure_breakout: bool = False
    breakout_lookback: int = 12      # Donchian lookback (uses [1] — no lookahead)
    breakout_atr_mult: float = 1.0   # min bar range as multiple of risk ATR
    max_breakout_dots: int = 1       # max breakout entries per ribbon arm


# --- ta.* helpers (matched to Pine semantics) -------------------------------
def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def _rma(s: pd.Series, n: int) -> pd.Series:
    # Wilder's moving average, as used inside Pine's ta.atr
    return s.ewm(alpha=1.0 / n, adjust=False).mean()


def _atr(df: pd.DataFrame, n: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return _rma(tr, n)


def _crossover(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a > b) & (a.shift(1) <= b.shift(1))


def _crossunder(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a < b) & (a.shift(1) >= b.shift(1))


def _barssince(cond: pd.Series) -> pd.Series:
    """Bars since `cond` was last True (0 on the True bar). NaN before first True."""
    n = len(cond)
    last_true = np.where(cond.values, np.arange(n), np.nan)
    last_true = pd.Series(last_true, index=cond.index).ffill().values
    out = np.arange(n) - last_true
    return pd.Series(out, index=cond.index)


def compute_signals(df: pd.DataFrame, p: RibbonParams = RibbonParams()) -> pd.DataFrame:
    df = df.copy()

    fast_ma = _ema(df["close"], p.ma1_length)
    slow_ma = _sma(df["close"], p.ma2_length)
    df["fast_ma"], df["slow_ma"] = fast_ma, slow_ma

    ema20_4h, ema50_4h = df["ema20_4h"], df["ema50_4h"]

    # --- Yang-Zhang sigma-angle (optional chop gate) ---
    if p.use_sigma_angle:
        yz_sigma = yang_zhang_sigma(df, p.yz_sigma_len)
        ics_angle = ics_trend_angle(df["close"], yz_sigma, p.angle_lookback)
    else:
        ics_angle = pd.Series(np.nan, index=df.index)
    df["ics_angle"] = ics_angle

    # --- Engine 1: Chop Killer (50 SMA slope) ---
    bull_slope = (slow_ma - slow_ma.shift(5)) / slow_ma.shift(5) * 100
    bear_slope = (slow_ma.shift(5) - slow_ma) / slow_ma.shift(5) * 100
    is_choppy_bull = bull_slope < p.min_slope
    is_choppy_bear = bear_slope < p.min_slope

    # --- Engine 2: Price Rocket Override ---
    macro_atr = _atr(df, p.macro_atr_len)
    safe_atr = macro_atr.clip(lower=0.0001)
    price_thrust_bull = (df["close"] - df["close"].shift(p.thrust_lookback)) / safe_atr
    price_thrust_bear = (df["close"].shift(p.thrust_lookback) - df["close"]) / safe_atr
    is_rocket_bull = (fast_ma > slow_ma) & (price_thrust_bull >= p.thrust_req)
    is_rocket_bear = (fast_ma < slow_ma) & (price_thrust_bear >= p.thrust_req)

    # --- Core gap ---
    gap_atr = (fast_ma - slow_ma).abs() / safe_atr

    # --- Counter-trend matrix (pure 4H logic) ---
    pure_bg_bull = ema20_4h > ema50_4h
    pure_bg_bear = ema20_4h < ema50_4h
    is_ct_bull = pure_bg_bear
    is_ct_bear = pure_bg_bull
    bars_bull = _barssince(_crossover(fast_ma, slow_ma))
    bars_bear = _barssince(_crossunder(fast_ma, slow_ma))
    ct_exhausted_bull = (is_ct_bull & (bars_bull >= p.ct_max_bars)).fillna(False)
    ct_exhausted_bear = (is_ct_bear & (bars_bear >= p.ct_max_bars)).fillna(False)

    # --- Ignition triggers ---
    std_bull = (fast_ma > slow_ma) & (gap_atr >= p.req_gap) & (~is_choppy_bull)
    std_bear = (fast_ma < slow_ma) & (gap_atr >= p.req_gap) & (~is_choppy_bear)
    trigger_bull = (std_bull | is_rocket_bull) & (~ct_exhausted_bull)
    trigger_bear = (std_bear | is_rocket_bear) & (~ct_exhausted_bear)

    cross_under = _crossunder(fast_ma, slow_ma)
    cross_over = _crossover(fast_ma, slow_ma)

    # --- Stateful latch + first-strike retest (iterative, matches Pine order) ---
    close = df["close"].values
    low = df["low"].values
    high = df["high"].values
    slow_v = slow_ma.values
    fast_v = fast_ma.values
    e20_v = ema20_4h.values
    e50_v = ema50_4h.values
    angle_v = ics_angle.values

    tb = trigger_bull.values
    ts = trigger_bear.values
    rb = is_rocket_bull.values
    rs = is_rocket_bear.values
    cu = cross_under.values
    co = cross_over.values
    ceb = ct_exhausted_bull.values
    ces = ct_exhausted_bear.values

    n = len(df)
    bull_ign = np.zeros(n, dtype=bool)
    bear_ign = np.zeros(n, dtype=bool)
    bull_dot = np.zeros(n, dtype=bool)
    bear_dot = np.zeros(n, dtype=bool)
    bull_dot_kind = np.full(n, None, dtype=object)
    bear_dot_kind = np.full(n, None, dtype=object)

    # Donchian channels for structure breakout (shifted — no lookahead)
    if p.use_structure_breakout:
        lb = max(2, p.breakout_lookback)
        don_hi = df["high"].rolling(lb).max().shift(1).values
        don_lo = df["low"].rolling(lb).min().shift(1).values
        bar_range = (df["high"] - df["low"]).values
        risk_atr_pre = _atr(df, p.risk_atr_len).values
    else:
        don_hi = don_lo = bar_range = risk_atr_pre = None

    bull_state = False
    bear_state = False
    bull_hits = 0
    bear_hits = 0
    bull_bo_hits = 0
    bear_bo_hits = 0

    for i in range(n):
        # 1) arm
        if tb[i]:
            bull_state = True
        if ts[i]:
            bear_state = True
        # 2) disarm (same-bar, after arming — matches Pine evaluation order)
        if (close[i] < slow_v[i]) or cu[i] or ceb[i]:
            bull_state = False
        if (close[i] > slow_v[i]) or co[i] or ces[i]:
            bear_state = False
        # 3) reset hit counters when disarmed
        if not bull_state:
            bull_hits = 0
            bull_bo_hits = 0
        if not bear_state:
            bear_hits = 0
            bear_bo_hits = 0
        # 4) retest + optional rocket expansion dots
        if not np.isnan(fast_v[i]):
            htf_ok_bull = (not p.require_htf_align) or (e20_v[i] > e50_v[i])
            htf_ok_bear = (not p.require_htf_align) or (e20_v[i] < e50_v[i])

            # sigma-angle chop gate: require enough trend strength (and optional sign match)
            if p.use_sigma_angle:
                a = angle_v[i]
                ang_strong = (not np.isnan(a)) and (abs(a) >= p.angle_thresh_deg)
                ang_ok_bull = ang_strong and ((not p.angle_directional) or a > 0)
                ang_ok_bear = ang_strong and ((not p.angle_directional) or a < 0)
            else:
                ang_ok_bull = ang_ok_bear = True

            max_dots = max(1, p.max_retest_dots)
            fired_bull = fired_bear = False

            if bull_state and htf_ok_bull and ang_ok_bull and bull_hits < max_dots:
                if (low[i] <= fast_v[i]) and (close[i] >= slow_v[i]):
                    bull_dot[i] = True
                    bull_dot_kind[i] = "retest"
                    bull_hits += 1
                    fired_bull = True
                elif p.fire_rocket_dot and not fired_bull and rb[i]:
                    bull_dot[i] = True
                    bull_dot_kind[i] = "rocket"
                    bull_hits += 1
                    fired_bull = True

            if bear_state and htf_ok_bear and ang_ok_bear and bear_hits < max_dots:
                if (high[i] >= fast_v[i]) and (close[i] <= slow_v[i]):
                    bear_dot[i] = True
                    bear_dot_kind[i] = "retest"
                    bear_hits += 1
                    fired_bear = True
                elif p.fire_rocket_dot and not fired_bear and rs[i]:
                    bear_dot[i] = True
                    bear_dot_kind[i] = "rocket"
                    bear_hits += 1
                    fired_bear = True

            # Structure breakout (expansion capture — non-ribbon)
            if p.use_structure_breakout and not np.isnan(fast_v[i]):
                max_bo = max(1, p.max_breakout_dots)
                bo_range_ok = bar_range[i] >= p.breakout_atr_mult * risk_atr_pre[i]
                if (bull_state and htf_ok_bull and ang_ok_bull and bull_bo_hits < max_bo
                        and not bull_dot[i] and bo_range_ok
                        and not np.isnan(don_hi[i]) and close[i] > don_hi[i]):
                    bull_dot[i] = True
                    bull_dot_kind[i] = "breakout"
                    bull_bo_hits += 1
                if (bear_state and htf_ok_bear and ang_ok_bear and bear_bo_hits < max_bo
                        and not bear_dot[i] and bo_range_ok
                        and not np.isnan(don_lo[i]) and close[i] < don_lo[i]):
                    bear_dot[i] = True
                    bear_dot_kind[i] = "breakout"
                    bear_bo_hits += 1

        bull_ign[i] = bull_state
        bear_ign[i] = bear_state

    df["bull_ignited"] = bull_ign
    df["bear_ignited"] = bear_ign
    df["bull_dot"] = bull_dot
    df["bear_dot"] = bear_dot
    df["bull_dot_kind"] = bull_dot_kind
    df["bear_dot_kind"] = bear_dot_kind
    df["risk_atr"] = _atr(df, p.risk_atr_len)
    return df
