#!/usr/bin/env python3
"""
run_extended_validation.py — free workaround for longer backtest history.

yfinance caps 15m data at ~60 days. Run the SAME MAIN baseline on 1h bars for
up to ~730 days as a parallel sanity check (not a replacement for live 15m).

Usage:
  python backtester/run_extended_validation.py --symbol GBPAUD=X
  python backtester/run_extended_validation.py --all-main
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import data_providers as dp
from backtest import RiskParams, compute_metrics, run_backtest
from fv_ribbon import RibbonParams, compute_signals
from macro_filter import MacroParams, align_strength_to_signals, load_macro_strength

try:
    from app.trading_config import ASSET_MACRO, DEFAULT_MACRO
except ImportError:
    ASSET_MACRO = {
        "EURUSD": {"pmi_source": "ism", "require_non_neutral": False},
        "GBPUSD": {"pmi_source": "ism", "require_non_neutral": False},
        "GBPAUD": {"pmi_source": "ism", "require_non_neutral": False},
        "AUDUSD": {"pmi_source": "oecd", "require_non_neutral": False},
        "NZDUSD": {"pmi_source": "oecd", "require_non_neutral": True},
        "USDJPY": {"pmi_source": "ism", "require_non_neutral": False},
        "USDCHF": {"pmi_source": "ism", "require_non_neutral": False},
    }
    DEFAULT_MACRO = {"pmi_source": "oecd", "require_non_neutral": False}

MAIN_UNIVERSE = [
    "EURUSD=X", "GBPUSD=X", "GBPAUD=X", "AUDUSD=X",
    "NZDUSD=X", "USDJPY=X", "USDCHF=X",
]

BASELINE = RibbonParams()
RISK = RiskParams(1.5, 1.5)


def macro_cfg(sym: str) -> dict:
    return ASSET_MACRO.get(sym.upper().replace("=X", ""), DEFAULT_MACRO)


def run_one(yf_sym: str, interval: str, period: str, macro_cache: dict) -> dict:
    sym = yf_sym.replace("=X", "")
    px = dp.attach_htf_shield(dp.fetch_price(yf_sym, interval, period), "4h", 20, 50)
    if len(px) < 200:
        return {"symbol": sym, "error": f"insufficient bars ({len(px)})"}

    mc = macro_cfg(sym)
    pmi = mc["pmi_source"]
    if pmi not in macro_cache:
        macro_cache[pmi] = load_macro_strength(pmi)
    strength = align_strength_to_signals(px.index, macro_cache[pmi])
    macro_p = MacroParams(not mc["require_non_neutral"])

    sig = compute_signals(px, BASELINE)
    trades = run_backtest(sig, sym, RISK, strength, macro_p)
    m = compute_metrics(trades)
    return {"symbol": sym, "interval": interval, "period": period, "bars": len(sig), "trades": len(trades), **m}


def main():
    ap = argparse.ArgumentParser(description="Extended 1h validation (free yfinance history)")
    ap.add_argument("--symbol", default="GBPAUD=X")
    ap.add_argument("--all-main", action="store_true")
    ap.add_argument("--interval", default="1h")
    ap.add_argument("--period", default="730d")
    args = ap.parse_args()

    symbols = MAIN_UNIVERSE if args.all_main else [args.symbol]
    macro_cache: dict = {}
    print(f"Extended validation | interval={args.interval} period={args.period} | POST-macro | set-and-forget (no disarm exit)\n")
    for sym in symbols:
        r = run_one(sym, args.interval, args.period, macro_cache)
        if "error" in r:
            print(f"  {r['symbol']:8}  ERROR: {r['error']}")
            continue
        print(
            f"  {r['symbol']:8}  bars={r['bars']:5}  trades={r['trades']:3}  "
            f"Sharpe={r.get('sharpe_ratio', 0):.2f}  WR={r.get('win_rate', 0):.1%}  "
            f"PF={r.get('profit_factor', 0):.2f}"
        )
    if args.interval == "15m":
        print("\nNote: 15m yfinance is capped ~60d. Use --interval 1h --period 730d for long history.")


if __name__ == "__main__":
    main()
