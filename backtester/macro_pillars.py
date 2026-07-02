"""
macro_pillars.py — USD macro engine (Layer 2), data-driven from FRED.

Core 6 pillars (backtest-compatible):
    FOMC +3, CPI +2, 10Y +2, NFP +2, PMI +2, Retail +1  → max ±12

Extended pillars (live engine, extended=True):
    DXY +2, Core PCE +2, PPI +1, Jobless Claims +1,
    Unemployment +1, Industrial Production +1, 2Y Yields +1  → +9 more

NO-LOOKAHEAD: publication lag on every series.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field

try:
    from .data_providers import _fetch_fred_series
except ImportError:
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
    series_b: str | None = None  # optional second series (ISM composite)
    invert_score: bool = False   # e.g. rising unemployment = USD negative


def _core_pillars(pmi_source: str) -> list[Pillar]:
    base = [
        Pillar("fomc",         "DFEDTARU",        3, "level_change_hold", 180, 2),
        Pillar("cpi",          "CPIAUCSL",        2, "yoy_accel",           3, 45),
        Pillar("yields",       "DGS10",           2, "level_change",       60, 1),
        Pillar("nfp",          "PAYEMS",          2, "mom_vs_avg",         12, 35),
        Pillar("retail_sales", "RSAFS",           1, "mom_pct",             1, 45),
    ]
    if pmi_source == "ism":
        pmi = Pillar("pmi", "IPMAN", 2, "ism_composite_delta", 1, 30, series_b="UMCSENT")
    else:
        pmi = Pillar("pmi", "BSCICP03USM665S", 2, "level_vs_100", 3, 30)
    return base[:4] + [pmi] + base[4:]


def _extended_pillars() -> list[Pillar]:
    """Additional FRED series for live USD engine (V5.6.1+)."""
    return [
        Pillar("dxy",    "DTWEXBGS",  2, "level_change", 60, 1),   # broad USD index
        Pillar("pce",    "PCEPILFE",  2, "yoy_accel",     3, 45),   # core PCE (Fed target)
        Pillar("ppi",    "PPIFIS",    1, "mom_pct",       1, 35),   # pipeline inflation
        Pillar("claims", "ICSA",      1, "level_change",  4, 7, invert_score=True),
        Pillar("unrate", "UNRATE",    1, "level_change",  3, 35, invert_score=True),
        Pillar("indpro", "INDPRO",    1, "mom_pct",       1, 35),   # industrial output
        Pillar("dgs2",   "DGS2",      1, "level_change", 60, 1),   # front-end rates
    ]


def pillars_for(pmi_source: str = "oecd", extended: bool = False) -> list[Pillar]:
    """Build pillar list. extended=True adds 7 live-only dollar drivers."""
    pillars = _core_pillars(pmi_source)
    if extended:
        pillars = pillars + _extended_pillars()
    return pillars

# Human-readable status names (match your live engine's vocabulary)
STATUS = {
    "fomc":         ("HAWKISH", "DOVISH"),
    "cpi":          ("HOT", "COLD"),
    "yields":       ("RISING", "FALLING"),
    "nfp":          ("STRONG", "WEAK"),
    "pmi":          ("EXPANSION", "CONTRACTION"),
    "retail_sales": ("STRONG", "WEAK"),
    "dxy":          ("STRONG", "WEAK"),
    "pce":          ("HOT", "COLD"),
    "ppi":          ("HOT", "COLD"),
    "claims":       ("ELEVATED", "LOW"),
    "unrate":       ("TIGHT", "LOOSENING"),
    "indpro":       ("EXPANSION", "CONTRACTION"),
    "dgs2":         ("RISING", "FALLING"),
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
    if p.transform == "ism_composite_delta":
        # Raw MoM delta: manufacturing IP + consumer sentiment (services proxy)
        b = _fetch_fred_series(p.series_b) if p.series_b else None
        if b is not None:
            b = b.reindex(s.index).ffill()
            return s.diff(p.lookback) + b.diff(p.lookback)
        return s.diff(p.lookback)
    raise ValueError(f"unknown transform {p.transform}")


def _score_pillar(p: Pillar) -> pd.DataFrame:
    """Return a daily DataFrame with columns [<name>_score, <name>_status]."""
    raw = _fetch_fred_series(p.series)
    mom = _momentum(raw, p)

    score = pd.Series(0, index=mom.index, dtype=int)
    if p.invert_score:
        score[mom > p.deadband] = -p.weight
        score[mom < -p.deadband] = p.weight
    else:
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


def build_macro_strength(pillars: list[Pillar] | None = None,
                         pmi_source: str = "oecd",
                         extended: bool = False) -> pd.DataFrame:
    """
    Returns daily DataFrame with pillar scores + usd_strength + market_state.
    extended=True adds 7 live dollar drivers (used by production webhook).
    """
    if pillars is None:
        pillars = pillars_for(pmi_source, extended=extended)
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

    max_abs = sum(p.weight for p in pillars)
    wreck = max(8, int(max_abs * 0.55))
    collapse = -wreck
    neutral_band = max(3, int(max_abs * 0.2))

    def _state(v: int) -> str:
        if v >= wreck:
            return "Wrecking Ball"
        if v <= collapse:
            return "USD Collapse"
        if -neutral_band <= v <= neutral_band:
            return "Choppy / Neutral"
        return "Trending Bias"

    macro["market_state"] = macro["usd_strength"].apply(_state)
    return macro


if __name__ == "__main__":
    print("Fetching 6-pillar macro from FRED (no key)...\n")
    macro = build_macro_strength()

    latest = macro.dropna(subset=["usd_strength"]).iloc[-1]
    print("=== LIVE PILLAR READOUT (most recent, lag-adjusted) ===")
    for p in pillars_for("oecd"):
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
