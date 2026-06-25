"""
macro_filter.py — Layer 2 "Analysis Brief" (the Weight of the Dollar).

Turns the hardcoded MACRO_CACHE concept into a DATA-DRIVEN, no-lookahead filter.

Thesis being tested:
  A Layer 1 technical signal only has a true edge when it aligns with the
  structural USD regime. For USD-quote pairs (GBPUSD, AUDUSD, EURUSD...):
      strong/rising USD  -> pair pressured DOWN -> only SHORTs allowed
      weak/falling USD   -> pair supported UP   -> only LONGs allowed
      neutral            -> defer to technicals (configurable)

USD regime score is built from:
  - DXY (broad dollar index) trend over `lookback` days
  - 10Y Treasury yield trend over `lookback` days
Each contributes +1 (rising) or -1 (falling); summed and thresholded.
"""

from __future__ import annotations
import pandas as pd
import numpy as np
from dataclasses import dataclass


@dataclass
class MacroParams:
    lookback_days: int = 20    # trend window for DXY / yields
    allow_neutral: bool = True # in filtered mode, let technicals pass when USD is neutral


def compute_usd_bias(macro: pd.DataFrame, p: MacroParams = MacroParams()) -> pd.DataFrame:
    """
    macro: daily frame with columns dxy, y10 (y2 optional).
    Returns daily frame with an integer `usd_bias` in {-1, 0, +1}
    (+1 = structurally strong USD, -1 = weak USD).
    """
    m = macro.copy()
    dxy_up = m["dxy"] > m["dxy"].shift(p.lookback_days)
    y10_up = m["y10"] > m["y10"].shift(p.lookback_days)

    score = (dxy_up.astype(int) - (~dxy_up).astype(int)) \
          + (y10_up.astype(int) - (~y10_up).astype(int))   # range: -2 .. +2

    usd_bias = pd.Series(0, index=m.index, dtype=int)
    usd_bias[score > 0] = 1
    usd_bias[score < 0] = -1

    out = pd.DataFrame({"usd_bias": usd_bias, "macro_score": score})
    # invalidate the warmup window (shift introduced NaNs -> treat as neutral 0)
    out.loc[m["dxy"].shift(p.lookback_days).isna(), ["usd_bias", "macro_score"]] = 0
    return out


def align_bias_to_signals(signal_index: pd.DatetimeIndex,
                          usd_bias: pd.DataFrame) -> pd.Series:
    """
    Attach each (intraday) signal bar to the most recent daily USD bias
    available on or before it. merge_asof backward => strictly no lookahead.
    """
    left = pd.DataFrame({"ts": pd.DatetimeIndex(signal_index).astype("datetime64[ns]")})
    left = left.sort_values("ts")
    right = usd_bias.reset_index()
    right.columns = ["ts"] + list(right.columns[1:])
    right["ts"] = pd.to_datetime(right["ts"]).astype("datetime64[ns]")
    right = right.sort_values("ts")
    merged = pd.merge_asof(left, right, on="ts", direction="backward")
    merged = merged.set_index("ts")
    return merged["usd_bias"].reindex(signal_index).fillna(0).astype(int)


def pair_directional_bias(pair: str, usd_bias: int) -> int:
    """
    Translate USD regime into an allowed direction for a specific pair.
    +1 => favours LONG, -1 => favours SHORT, 0 => neutral.
    """
    sym = pair.upper().replace("=X", "").replace("/", "").replace("-", "")
    if sym.endswith("USD"):      # e.g. GBPUSD, AUDUSD, EURUSD -> USD is the quote
        return -usd_bias
    if sym.startswith("USD"):    # e.g. USDJPY, USDCAD -> USD is the base
        return usd_bias
    return 0                     # non-USD cross -> macro filter abstains


def trade_allowed(pair: str, direction: str, usd_bias: int, p: MacroParams) -> bool:
    """direction: 'LONG' or 'SHORT'. Returns True if the macro brief permits it."""
    bias = pair_directional_bias(pair, usd_bias)
    if bias == 0:
        return p.allow_neutral
    if direction == "LONG":
        return bias > 0
    return bias < 0
