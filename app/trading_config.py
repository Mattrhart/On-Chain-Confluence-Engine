"""
trading_config.py — optimizer-derived Layer 2 settings per asset.

Re-run `backtester/optimize.py` and update this file when re-tuning.
Layer 1 Pine params are hardcoded in strategies/*.pine.
"""

from __future__ import annotations

# PMI source for 6-pillar macro cache key ("oecd" | "ism")
# require_non_neutral: block trades when macro bias == 0 (optimizer --no-neutral)
ASSET_MACRO: dict[str, dict] = {
    "ETHUSD":  {"pmi_source": "ism",  "require_non_neutral": False},
    "ETHUSDT": {"pmi_source": "ism",  "require_non_neutral": False},
    "EURUSD":  {"pmi_source": "ism",  "require_non_neutral": False},
    "GBPUSD":  {"pmi_source": "ism",  "require_non_neutral": False},
    "AUDUSD":  {"pmi_source": "oecd", "require_non_neutral": False},
    "NZDUSD":  {"pmi_source": "oecd", "require_non_neutral": True},
    "USDJPY":  {"pmi_source": "ism",  "require_non_neutral": False},
    "USDCHF":  {"pmi_source": "ism",  "require_non_neutral": False},
}

DEFAULT_MACRO = {"pmi_source": "oecd", "require_non_neutral": False}


def macro_settings_for_ticker(raw_ticker: str) -> dict:
    sym = raw_ticker.upper().replace("/", "").replace("-", "").replace(" ", "")
    return ASSET_MACRO.get(sym, DEFAULT_MACRO)
