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

    tb = trigger_bull.values
    ts = trigger_bear.values
    cu = cross_under.values
    co = cross_over.values
    ceb = ct_exhausted_bull.values
    ces = ct_exhausted_bear.values

    n = len(df)
    bull_ign = np.zeros(n, dtype=bool)
    bear_ign = np.zeros(n, dtype=bool)
    bull_dot = np.zeros(n, dtype=bool)
    bear_dot = np.zeros(n, dtype=bool)

    bull_state = False
    bear_state = False
    bull_hits = 0
    bear_hits = 0

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
        if not bear_state:
            bear_hits = 0
        # 4) first-strike retest dot (barstate.isconfirmed is always true on closed bars)
        if not np.isnan(fast_v[i]):
            htf_ok_bull = (not p.require_htf_align) or (e20_v[i] > e50_v[i])
            htf_ok_bear = (not p.require_htf_align) or (e20_v[i] < e50_v[i])
            if bull_state and htf_ok_bull and (low[i] <= fast_v[i]) and (close[i] >= slow_v[i]) and bull_hits < 1:
                bull_dot[i] = True
                bull_hits += 1
            if bear_state and htf_ok_bear and (high[i] >= fast_v[i]) and (close[i] <= slow_v[i]) and bear_hits < 1:
                bear_dot[i] = True
                bear_hits += 1

        bull_ign[i] = bull_state
        bear_ign[i] = bear_state

    df["bull_ignited"] = bull_ign
    df["bear_ignited"] = bear_ign
    df["bull_dot"] = bull_dot
    df["bear_dot"] = bear_dot
    df["risk_atr"] = _atr(df, p.risk_atr_len)
    return df
