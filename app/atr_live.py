"""
atr_live.py — compute ATR(14) on webhook for Telegram stop levels.

Avoids {{plot()}} in TradingView alert JSON (wraps / NaN / invalid JSON).
Uses Wilder ATR(14) — same formula as backtester/fv_ribbon._atr.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
_BT = _ROOT / "backtester"
if str(_BT) not in sys.path:
    sys.path.insert(0, str(_BT))

from data_providers import fetch_price

RISK_ATR_LEN = 14

_YF: dict[str, str] = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "AUDUSD": "AUDUSD=X",
    "NZDUSD": "NZDUSD=X", "USDJPY": "USDJPY=X", "USDCHF": "USDCHF=X",
    "GBPAUD": "GBPAUD=X", "EURGBP": "EURGBP=X", "USDCAD": "USDCAD=X",
    "ETHUSD": "ETH-USD", "ETHUSDT": "ETH-USD",
    "BTCUSD": "BTC-USD", "SOLUSD": "SOL-USD",
}


def _norm(ticker: str) -> str:
    t = ticker.upper().replace("/", "").replace("-", "").replace(" ", "").split(":")[-1]
    for stable in ("USDT", "USDC"):
        if t.endswith(stable) and t != stable:
            base = t[: -len(stable)]
            return base + "USD" if base else t
    return t


def _to_yf(sym: str) -> str:
    if sym in _YF:
        return _YF[sym]
    if len(sym) == 6 and sym.isalpha():
        return f"{sym}=X"
    if sym.endswith("USD") and len(sym) > 3:
        return f"{sym[:-3]}-USD"
    return sym


def _interval_from_tf(timeframe: str) -> str:
    tf = (timeframe or "15").strip().lower().replace("m", "")
    if tf == "60":
        return "1h"
    if tf in ("1", "5", "15", "30", "240"):
        return f"{tf}m"
    return "15m"


def _wilder_atr(df: pd.DataFrame, n: int = RISK_ATR_LEN) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()


def fetch_live_risk_atr(ticker: str, timeframe: str = "15") -> float | None:
    """Live ATR(14) for Telegram stop levels (matches backtester risk_atr)."""
    yf_sym = _to_yf(_norm(ticker))
    interval = _interval_from_tf(timeframe)
    period = "60d" if interval in ("15m", "5m", "1m") else "730d"
    try:
        df = fetch_price(yf_sym, interval=interval, period=period)
        if len(df) < RISK_ATR_LEN + 2:
            return None
        val = float(_wilder_atr(df).iloc[-1])
        if val != val or val <= 0:
            return None
        return val
    except Exception as exc:
        print(f"[atr_live] fetch failed {yf_sym} {interval}: {exc}")
        return None
