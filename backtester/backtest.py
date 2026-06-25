"""
backtest.py — event-driven trade simulator + performance metrics.

Risk model mirrors strategy_backtest.pine:
  - enter at the close of the signal (dot) bar  (process_orders_on_close)
  - stop  = entry -/+ atr_sl_mult * risk_atr
  - target = entry +/- atr_sl_mult * risk_atr * rr_target
  - optional: exit when the ribbon disarms
  - one position at a time (no pyramiding); if stop & target hit in the same
    bar, the STOP is assumed first (conservative).

P&L is tracked in R-multiples (sizing-agnostic). Equity curve assumes a fixed
fractional risk per trade so we can compute a comparable max drawdown.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field

from macro_filter import MacroParams, trade_allowed


@dataclass
class RiskParams:
    atr_sl_mult: float = 1.5
    rr_target: float = 1.5
    exit_on_disarm: bool = True
    allow_longs: bool = True
    allow_shorts: bool = True
    risk_per_trade: float = 0.01   # fraction of equity risked per trade (for the curve)


@dataclass
class Trade:
    direction: str
    entry_time: pd.Timestamp
    entry: float
    exit_time: pd.Timestamp
    exit: float
    r_multiple: float
    reason: str


def run_backtest(df: pd.DataFrame,
                 pair: str,
                 risk: RiskParams = RiskParams(),
                 usd_strength_series: pd.Series | None = None,
                 macro_p: MacroParams = MacroParams()) -> list[Trade]:
    """
    df must contain: high, low, close, bull_dot, bear_dot, bull_ignited,
                     bear_ignited, risk_atr.
    If usd_strength_series is provided, the 6-pillar Layer 2 macro filter is applied.
    """
    idx = df.index
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    rib_bull = df["bull_ignited"].values
    rib_bear = df["bear_ignited"].values
    bull_dot = df["bull_dot"].values
    bear_dot = df["bear_dot"].values
    atr = df["risk_atr"].values

    strength = (usd_strength_series.reindex(idx).fillna(0).astype(int).values
                if usd_strength_series is not None else None)

    trades: list[Trade] = []
    n = len(df)
    i = 0
    while i < n:
        want_long = bull_dot[i] and risk.allow_longs
        want_short = bear_dot[i] and risk.allow_shorts
        if not (want_long or want_short):
            i += 1
            continue
        if np.isnan(atr[i]) or atr[i] <= 0:
            i += 1
            continue

        direction = "LONG" if want_long else "SHORT"

        # Layer 2 macro gate (6-pillar usd_strength)
        if strength is not None and not trade_allowed(pair, direction, int(strength[i]), macro_p):
            i += 1
            continue

        entry = close[i]
        r = risk.atr_sl_mult * atr[i]
        if direction == "LONG":
            stop = entry - r
            target = entry + r * risk.rr_target
        else:
            stop = entry + r
            target = entry - r * risk.rr_target

        # walk forward to resolve the trade
        j = i + 1
        exit_price, exit_time, reason, r_mult = None, None, None, None
        while j < n:
            hi, lo = high[j], low[j]
            if direction == "LONG":
                hit_stop = lo <= stop
                hit_tgt = hi >= target
                if hit_stop:                       # stop-first convention
                    exit_price, reason, r_mult = stop, "stop", -1.0
                elif hit_tgt:
                    exit_price, reason, r_mult = target, "target", risk.rr_target
                elif risk.exit_on_disarm and not rib_bull[j]:
                    exit_price, reason = close[j], "disarm"
                    r_mult = (close[j] - entry) / r
            else:
                hit_stop = hi >= stop
                hit_tgt = lo <= target
                if hit_stop:
                    exit_price, reason, r_mult = stop, "stop", -1.0
                elif hit_tgt:
                    exit_price, reason, r_mult = target, "target", risk.rr_target
                elif risk.exit_on_disarm and not rib_bear[j]:
                    exit_price, reason = close[j], "disarm"
                    r_mult = (entry - close[j]) / r
            if exit_price is not None:
                exit_time = idx[j]
                break
            j += 1

        if exit_price is None:                     # ran out of data -> close at last bar
            j = n - 1
            exit_price, exit_time, reason = close[j], idx[j], "eod"
            r_mult = ((close[j] - entry) if direction == "LONG" else (entry - close[j])) / r

        trades.append(Trade(direction, idx[i], entry, exit_time, exit_price, float(r_mult), reason))
        i = j + 1   # one position at a time: resume after the exit bar
    return trades


# ---------------------------------------------------------------------------
# METRICS
# ---------------------------------------------------------------------------
def compute_metrics(trades: list[Trade], risk_per_trade: float = 0.01,
                    bars_per_year: float = 8760.0) -> dict:
    empty = {"trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "expectancy_R": 0.0,
             "total_R": 0.0, "max_drawdown_pct": 0.0, "return_pct": 0.0,
             "avg_win_R": 0.0, "avg_loss_R": 0.0, "sharpe_ratio": 0.0}
    if not trades:
        return empty

    r = np.array([t.r_multiple for t in trades])
    wins = r[r > 0]
    losses = r[r <= 0]
    gross_win = wins.sum()
    gross_loss = -losses.sum()

    # equity curve via fixed fractional risk
    equity = np.cumprod(1.0 + risk_per_trade * r)
    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / peak
    max_dd = drawdown.min() if len(drawdown) else 0.0

    # Annualized Sharpe from per-trade R-multiples
    std_r = r.std(ddof=1) if len(r) > 1 else 0.0
    span_days = max((trades[-1].exit_time - trades[0].entry_time).days, 1)
    trades_per_year = len(r) / span_days * 365.25
    if std_r > 0 and trades_per_year > 0:
        sharpe = (r.mean() / std_r) * np.sqrt(trades_per_year)
    else:
        sharpe = 0.0 if r.mean() <= 0 else float("inf")

    return {
        "trades": len(trades),
        "win_rate": round(100.0 * len(wins) / len(r), 1),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else float("inf"),
        "expectancy_R": round(r.mean(), 3),
        "total_R": round(r.sum(), 2),
        "avg_win_R": round(wins.mean(), 2) if len(wins) else 0.0,
        "avg_loss_R": round(losses.mean(), 2) if len(losses) else 0.0,
        "max_drawdown_pct": round(100.0 * max_dd, 2),
        "return_pct": round(100.0 * (equity[-1] - 1.0), 2),
        "sharpe_ratio": round(float(sharpe), 3) if np.isfinite(sharpe) else sharpe,
    }
