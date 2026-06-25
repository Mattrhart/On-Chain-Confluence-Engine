"""
macro_pillars.py — the real 6-pillar USD macro engine (Layer 2), data-driven.

This replaces the static MACRO_CACHE dictionary from your live main.py with a
LIVE/HISTORICAL data feed from FRED (free, no API key via the fredgraph CSV
endpoint). It replicates your calculate_usd_macro_bias() scoring EXACTLY:

    FOMC          HAWKISH +3 / DOVISH -3
    CPI           HOT     +2 / COLD   -2
    10Y Yields    RISING  +2 / FALLING-2
    NFP (labor)   STRONG  +2 / WEAK   -2
    PMI           EXPANSION +2 / CONTRACTION -2
    Retail Sales  STRONG  +1 / WEAK   -1
    ----------------------------------------
    usd_strength range: -12 .. +12   (>=8 "Wrecking Ball", <=-8 "Collapse")

NO-LOOKAHEAD: each series is shifted forward by a realistic publication lag so a
backtest on date t only ever sees macro that was actually released by t.

PILLAR -> FRED SERIES
    FOMC          DFEDTARU  Fed funds target range, upper limit (daily)
    CPI           CPIAUCSL  CPI-U, all items, SA (monthly)
    10Y Yields    DGS10     10-Year Treasury constant maturity (daily)
    NFP           PAYEMS    Total nonfarm payrolls (monthly, level -> MoM change)
    Retail Sales  RSAFS     Advance retail & food services sales (monthly)
    PMI*          BSCICP03USM665S  OECD US Business Confidence (monthly, ~100 = neutral)

* ISM PMI is not freely redistributable on FRED, so we use the OECD Business
  Confidence Indicator as a documented proxy. Swap `series` below if you wire a
  real ISM/S&P Global PMI feed later — the scoring contract stays identical.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field

from data_providers import _fetch_fred_series


@dataclass
class Pillar:
    name: str
    series: str
    weight: int
    transform: str       # how raw data -> directional momentum
    lookback: int        # observations (months for monthly, days for daily)
    lag_days: int        # publication delay (no-lookahead)
    deadband: float = 0.0  # |momentum| <= deadband -> NEUTRAL (0)


PILLARS = [
    Pillar("fomc",         "DFEDTARU",        3, "level_change_hold", 180, 2),
    Pillar("cpi",          "CPIAUCSL",        2, "yoy_accel",           3, 45),
    Pillar("yields",       "DGS10",           2, "level_change",       60, 1),
    Pillar("nfp",          "PAYEMS",          2, "mom_vs_avg",         12, 35),
    Pillar("pmi",          "BSCICP03USM665S", 2, "level_vs_100",        3, 30),
    Pillar("retail_sales", "RSAFS",           1, "mom_pct",             1, 45),
]

# Human-readable status names (match your live engine's vocabulary)
STATUS = {
    "fomc":         ("HAWKISH", "DOVISH"),
    "cpi":          ("HOT", "COLD"),
    "yields":       ("RISING", "FALLING"),
    "nfp":          ("STRONG", "WEAK"),
    "pmi":          ("EXPANSION", "CONTRACTION"),
    "retail_sales": ("STRONG", "WEAK"),
}


def _momentum(raw: pd.Series, p: Pillar) -> pd.Series:
    """Turn a raw FRED series into a signed momentum number per observation."""
    s = raw.dropna().astype(float)
    if p.transform == "level_change":
        return s - s.shift(p.lookback)
    if p.transform == "level_change_hold":
        # Hawkish if rising OR (flat AND elevated vs 2y median). Dovish if cutting.
        chg = s - s.shift(p.lookback)
        med = s.rolling(504, min_periods=60).median()   # ~2y of business days
        hold_high = (chg.abs() < 1e-9) & (s >= med)
        out = chg.copy()
        out[hold_high] = 1.0     # treat "hawkish hold" as positive
        return out
    if p.transform == "yoy_accel":
        yoy = s.pct_change(12) * 100.0
        accel = yoy - yoy.shift(p.lookback)
        # HOT if accelerating OR yoy>3%; COLD if decelerating and yoy<2.5%
        out = accel.copy()
        out[yoy > 3.0] = out[yoy > 3.0].abs() + 1.0
        out[(accel < 0) & (yoy < 2.5)] = -(out[(accel < 0) & (yoy < 2.5)].abs() + 1.0)
        return out
    if p.transform == "mom_vs_avg":
        mom = s.diff()
        return mom - mom.rolling(p.lookback).mean()
    if p.transform == "mom_pct":
        return s.pct_change(p.lookback) * 100.0
    if p.transform == "level_vs_100":
        return s - 100.0
    raise ValueError(f"unknown transform {p.transform}")


def _score_pillar(p: Pillar) -> pd.DataFrame:
    """Return a daily DataFrame with columns [<name>_score, <name>_status]."""
    raw = _fetch_fred_series(p.series)
    mom = _momentum(raw, p)

    score = pd.Series(0, index=mom.index, dtype=int)
    score[mom > p.deadband] = p.weight
    score[mom < -p.deadband] = -p.weight

    pos, neg = STATUS[p.name]
    status = pd.Series("NEUTRAL", index=mom.index, dtype=object)
    status[score > 0] = pos
    status[score < 0] = neg

    df = pd.DataFrame({f"{p.name}_score": score, f"{p.name}_status": status})
    # publication lag => no lookahead: value effective lag_days AFTER observation
    df.index = pd.DatetimeIndex(df.index) + pd.Timedelta(days=p.lag_days)
    # expand to daily and forward-fill (a release stays in effect until the next)
    daily = df.resample("D").ffill()
    return daily


def build_macro_strength(pillars: list[Pillar] = PILLARS) -> pd.DataFrame:
    """
    Returns a daily DataFrame with each pillar's score/status plus:
        usd_strength : int  (-12 .. +12)  — replicates calculate_usd_macro_bias()
        market_state : str  (Wrecking Ball / Collapse / Trending / Choppy-Neutral)
    """
    frames = []
    for p in pillars:
        try:
            frames.append(_score_pillar(p))
        except Exception as e:  # pragma: no cover
            print(f"  [WARN] pillar '{p.name}' ({p.series}) failed: {e}")

    if not frames:
        raise RuntimeError("no macro pillars could be fetched")

    macro = pd.concat(frames, axis=1, sort=False).sort_index().ffill()
    score_cols = [c for c in macro.columns if c.endswith("_score")]
    macro[score_cols] = macro[score_cols].fillna(0)
    macro["usd_strength"] = macro[score_cols].sum(axis=1).astype(int)

    def _state(v: int) -> str:
        if v >= 8:
            return "Wrecking Ball"
        if v <= -8:
            return "USD Collapse"
        if -3 <= v <= 3:
            return "Choppy / Neutral"
        return "Trending Bias"

    macro["market_state"] = macro["usd_strength"].apply(_state)
    return macro


if __name__ == "__main__":
    print("Fetching 6-pillar macro from FRED (no key)...\n")
    macro = build_macro_strength()

    latest = macro.dropna(subset=["usd_strength"]).iloc[-1]
    print("=== LIVE PILLAR READOUT (most recent, lag-adjusted) ===")
    for p in PILLARS:
        sc = latest.get(f"{p.name}_score", 0)
        stt = latest.get(f"{p.name}_status", "—")
        sign = f"+{sc}" if sc > 0 else str(sc)
        print(f"  {p.name:<13} {str(stt):<12} ({sign})   [{p.series}]")
    print(f"\n  >>> usd_strength = {int(latest['usd_strength']):+d}   "
          f"MARKET STATE: {latest['market_state']}")
    print(f"      (your hand-typed MACRO_CACHE scored +12 'Wrecking Ball')\n")

    print("=== HISTORICAL usd_strength (quarterly snapshots, last ~3y) ===")
    q = macro["usd_strength"].resample("QE").last().dropna().tail(12)
    for ts, v in q.items():
        bar = "#" * abs(int(v))
        print(f"  {ts.date()}  {int(v):+3d}  {bar}")
