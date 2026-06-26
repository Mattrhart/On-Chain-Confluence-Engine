"""
trading_config.py — Layer 2 macro + per-asset stop routing for V5.5.2+

stop_mode:
  "atr"    — server computes stop/target from risk_atr in webhook (Telegram shows levels)
  "manual" — you place structure stop; Telegram notes manual mode only
"""

from __future__ import annotations

ASSET_MACRO: dict[str, dict] = {
    "ETHUSD":  {"pmi_source": "ism",  "require_non_neutral": False},
    "ETHUSDT": {"pmi_source": "ism",  "require_non_neutral": False},
    "EURUSD":  {"pmi_source": "ism",  "require_non_neutral": False},
    "GBPUSD":  {"pmi_source": "ism",  "require_non_neutral": False},
    "GBPAUD":  {"pmi_source": "ism",  "require_non_neutral": False},
    "AUDUSD":  {"pmi_source": "oecd", "require_non_neutral": False},
    "NZDUSD":  {"pmi_source": "oecd", "require_non_neutral": True},
    "USDJPY":  {"pmi_source": "ism",  "require_non_neutral": False},
    "USDCHF":  {"pmi_source": "ism",  "require_non_neutral": False},
}

DEFAULT_MACRO = {"pmi_source": "oecd", "require_non_neutral": False}

# Institutional audit: AUD/ETH/EUR/GBP stronger on ATR; NZD/CHF on structure (manual)
ASSET_RISK: dict[str, dict] = {
    "ETHUSD":  {"stop_mode": "atr", "atr_sl_mult": 1.5, "rr_target": 3.0},
    "ETHUSDT": {"stop_mode": "atr", "atr_sl_mult": 1.5, "rr_target": 3.0},
    "EURUSD":  {"stop_mode": "atr", "atr_sl_mult": 1.5, "rr_target": 1.5},
    "GBPUSD":  {"stop_mode": "atr", "atr_sl_mult": 1.5, "rr_target": 1.5},
    "GBPAUD":  {"stop_mode": "atr", "atr_sl_mult": 1.5, "rr_target": 1.5},
    "AUDUSD":  {"stop_mode": "atr", "atr_sl_mult": 1.5, "rr_target": 1.5},
    "BTCUSD":  {"stop_mode": "atr", "atr_sl_mult": 1.5, "rr_target": 1.5},
    "SOLUSD":  {"stop_mode": "atr", "atr_sl_mult": 1.5, "rr_target": 1.5},
    "NZDUSD":  {"stop_mode": "manual", "atr_sl_mult": 1.5, "rr_target": 1.5},
    "USDCHF":  {"stop_mode": "manual", "atr_sl_mult": 1.5, "rr_target": 1.5},
}

DEFAULT_RISK = {"stop_mode": "manual", "atr_sl_mult": 1.5, "rr_target": 1.5}


def _norm(raw_ticker: str) -> str:
    return raw_ticker.upper().replace("/", "").replace("-", "").replace(" ", "").split(":")[-1]


def macro_settings_for_ticker(raw_ticker: str) -> dict:
    return ASSET_MACRO.get(_norm(raw_ticker), DEFAULT_MACRO)


def risk_settings_for_ticker(raw_ticker: str) -> dict:
    sym = _norm(raw_ticker)
    for stable in ("USDT", "USDC", "USD"):
        if sym.endswith(stable) and sym != stable:
            base = sym[: -len(stable)]
            if base + "USD" in ASSET_RISK:
                return ASSET_RISK[base + "USD"]
            break
    return ASSET_RISK.get(sym, DEFAULT_RISK)


def compute_atr_levels(
    direction: str,
    entry: float,
    risk_atr: float,
    atr_sl_mult: float,
    rr_target: float,
) -> dict:
    """Stop/target from ATR risk model (matches backtester RiskParams)."""
    r = atr_sl_mult * risk_atr
    if direction == "LONG":
        stop = entry - r
        target = entry + r * rr_target
    else:
        stop = entry + r
        target = entry - r * rr_target
    return {"stop": stop, "target": target, "risk_points": r, "rr_target": rr_target}
