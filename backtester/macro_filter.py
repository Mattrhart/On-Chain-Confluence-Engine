"""
macro_filter.py — Layer 2 "Analysis Brief" (6-pillar USD macro engine).

Uses macro_pillars.build_macro_strength() — the same scoring contract as your live
main.py calculate_usd_macro_bias() (-12 .. +12), NOT the simplified DXY proxy.

Forex topology (matches main.py):
    XXXUSD  -> macro_bias_for_pair = -usd_strength
    USDXXX  -> macro_bias_for_pair = +usd_strength
Crypto (ETH, etc.):
    macro_bias = -usd_strength  (USD inverse correlation)

EXECUTE when direction aligns with macro_bias_for_pair; allow when bias == 0 if
allow_neutral is True (same as main.py flat macro branch).
"""

from __future__ import annotations
import pandas as pd
from dataclasses import dataclass

from macro_pillars import build_macro_strength

CRYPTO_PREFIXES = ("ETH", "BTC", "SOL", "BNB", "HYPE", "LINK", "PEPE", "AERO", "LDO", "WBTC")


@dataclass
class MacroParams:
    allow_neutral: bool = True


def normalize_pair(pair: str) -> str:
    return pair.upper().replace("=X", "").replace("/", "").replace("-", "").replace(" ", "")


def macro_bias_for_pair(pair: str, usd_strength: int) -> int:
    """
    Translate 6-pillar usd_strength into directional bias for this asset.
    Positive => favours LONG, negative => favours SHORT, 0 => neutral pass-through.
    """
    sym = normalize_pair(pair)
    if sym.endswith("USD"):
        return -usd_strength
    if sym.startswith("USD"):
        return usd_strength
    if any(sym.startswith(p) or sym.startswith(p + "USD") or sym.startswith(p + "USDT")
           for p in CRYPTO_PREFIXES):
        return -usd_strength
    return 0


def trade_allowed(pair: str, direction: str, usd_strength: int, p: MacroParams) -> bool:
    """Replicates main.py forex/crypto EXECUTE vs ABORT decision."""
    bias = macro_bias_for_pair(pair, usd_strength)
    if bias == 0:
        return p.allow_neutral
    if direction == "LONG":
        return bias > 0
    return bias < 0


def align_strength_to_signals(signal_index: pd.DatetimeIndex,
                              macro: pd.DataFrame) -> pd.Series:
    """
    Attach each intraday bar to the most recent daily usd_strength (no lookahead).
    """
    left = pd.DataFrame({"ts": pd.DatetimeIndex(signal_index).astype("datetime64[ns]")})
    left = left.sort_values("ts")
    right = macro[["usd_strength"]].copy()
    right.index.name = "ts"
    right = right.reset_index()
    right["ts"] = pd.to_datetime(right["ts"]).astype("datetime64[ns]")
    right = right.sort_values("ts")
    merged = pd.merge_asof(left, right, on="ts", direction="backward")
    merged = merged.set_index("ts")
    return merged["usd_strength"].reindex(signal_index).fillna(0).astype(int)


def load_macro_strength() -> pd.DataFrame:
    """Fetch/build the full 6-pillar daily macro frame."""
    return build_macro_strength()
