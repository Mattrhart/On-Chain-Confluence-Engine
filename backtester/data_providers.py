"""
data_providers.py — free market + macro data for the FV Ribbon backtester.

PRICE  : yfinance (Forex "GBPUSD=X" / "AUDUSD=X", crypto "BTC-USD", etc.)
MACRO  : FRED via the public fredgraph CSV endpoint (NO API key required)

Design rule that matters most here: NO LOOKAHEAD.
- The 4H higher-timeframe shield is aligned to each base bar using only the
  most-recently *closed* 4H bar (merge_asof backward). This mirrors the Pine
  `request.security(..., expr[1], lookahead_on)` non-repainting idiom.
- Daily macro series are aligned the same way: a signal at time t only ever
  sees macro data published on or before t.
"""

from __future__ import annotations
import io
import datetime as dt
import pandas as pd
import numpy as np
import requests

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None


# ---------------------------------------------------------------------------
# PRICE
# ---------------------------------------------------------------------------
def _normalize_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten yfinance output to lowercase open/high/low/close, tz-naive UTC."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    keep = [c for c in ["open", "high", "low", "close"] if c in df.columns]
    df = df[keep].copy()
    df = df[~df.index.duplicated(keep="last")]
    if df.index.tz is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    df.index = pd.DatetimeIndex(df.index).astype("datetime64[ns]")
    return df.dropna()


def fetch_price(symbol: str, interval: str = "1h", period: str = "730d") -> pd.DataFrame:
    """
    Pull OHLC candles from yfinance.

    interval: "1h" (~2yr history), "1d" (decades), "15m"/"5m"/"1m" (short window).
    Returns DataFrame indexed by tz-naive UTC datetime with open/high/low/close.
    """
    if yf is None:
        raise ImportError("yfinance not installed. Run: pip install -r requirements.txt")
    raw = yf.download(
        symbol, interval=interval, period=period,
        auto_adjust=False, progress=False, threads=False,
    )
    if raw is None or raw.empty:
        raise ValueError(f"No price data returned for {symbol} ({interval}/{period}).")
    return _normalize_ohlc(raw)


def attach_htf_shield(df: pd.DataFrame, htf_rule: str = "4h",
                      ema_fast: int = 20, ema_slow: int = 50) -> pd.DataFrame:
    """
    Resample to the higher timeframe, compute EMA(fast)/EMA(slow) on HTF closes,
    then align back to the base frame using ONLY the most-recently closed HTF bar.

    Adds columns: ema20_4h, ema50_4h  (named for continuity with the Pine script).
    """
    o = df["open"].resample(htf_rule, label="right", closed="right").first()
    h = df["high"].resample(htf_rule, label="right", closed="right").max()
    low = df["low"].resample(htf_rule, label="right", closed="right").min()
    c = df["close"].resample(htf_rule, label="right", closed="right").last()
    htf = pd.DataFrame({"open": o, "high": h, "low": low, "close": c}).dropna()

    htf["ema20_4h"] = htf["close"].ewm(span=ema_fast, adjust=False).mean()
    htf["ema50_4h"] = htf["close"].ewm(span=ema_slow, adjust=False).mean()

    # label="right" => index is the HTF bar's CLOSE time, so a backward merge_asof
    # only ever attaches a fully-closed HTF bar to each base bar. No lookahead.
    htf_aligned = htf[["ema20_4h", "ema50_4h"]].copy()
    htf_aligned.index.name = "ts"
    htf_aligned = htf_aligned.reset_index()

    base = df.copy()
    base.index.name = "ts"
    base = base.reset_index()

    merged = pd.merge_asof(
        base.sort_values("ts"),
        htf_aligned.sort_values("ts"),
        on="ts", direction="backward",
    ).set_index("ts")
    return merged.dropna(subset=["ema20_4h", "ema50_4h"])


# ---------------------------------------------------------------------------
# MACRO  (FRED fredgraph CSV — public, no key)
# ---------------------------------------------------------------------------
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"

# Default series for the "Weight of the Dollar" engine:
#   DTWEXBGS = Nominal Broad U.S. Dollar Index (DXY proxy, daily)
#   DGS10    = 10-Year Treasury Yield (daily)
#   DGS2     = 2-Year Treasury Yield (daily)
DEFAULT_MACRO_SERIES = {"dxy": "DTWEXBGS", "y10": "DGS10", "y2": "DGS2"}


def _fetch_fred_series(series_id: str, timeout: float = 20.0) -> pd.Series:
    url = FRED_CSV.format(series=series_id)
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    raw = pd.read_csv(io.StringIO(resp.text))
    date_col, val_col = raw.columns[0], raw.columns[1]
    raw[date_col] = pd.to_datetime(raw[date_col])
    # FRED encodes missing values as "."
    raw[val_col] = pd.to_numeric(raw[val_col], errors="coerce")
    s = raw.set_index(date_col)[val_col].rename(series_id)
    return s


def fetch_macro(series: dict | None = None) -> pd.DataFrame:
    """
    Returns a daily, forward-filled macro frame with columns: dxy, y10, y2.
    Index is tz-naive daily dates.
    """
    series = series or DEFAULT_MACRO_SERIES
    cols = {}
    for alias, sid in series.items():
        cols[alias] = _fetch_fred_series(sid)
    macro = pd.DataFrame(cols).sort_index().ffill().dropna(how="all")
    return macro


if __name__ == "__main__":  # quick manual check
    px = fetch_price("GBPUSD=X", "1h", "60d")
    px = attach_htf_shield(px)
    print("PRICE", px.shape, px.index.min(), "->", px.index.max())
    print(px.tail(3))
    mac = fetch_macro()
    print("MACRO", mac.shape)
    print(mac.tail(3))
