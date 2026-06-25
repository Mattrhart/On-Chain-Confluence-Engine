"""
run.py — FV Ribbon backtester harness.

The whole point: run the SAME signals twice — once raw (Layer 1 only) and once
through the "Weight of the Dollar" macro filter (Layer 1 + Layer 2) — and put the
numbers side by side. That comparison is the actual answer to whether the DXY
filter adds edge.

Examples
--------
    python run.py                              # GBPUSD + AUDUSD, 1h, ~2yr
    python run.py --pairs GBPUSD=X EURUSD=X
    python run.py --interval 1d --period 10y   # daily, deep history
    python run.py --rr 2.0 --atr-mult 1.5 --lookback 30
"""

from __future__ import annotations
import argparse
import sys
import pandas as pd
from tabulate import tabulate

import data_providers as dp
from fv_ribbon import RibbonParams, compute_signals
from macro_filter import MacroParams, compute_usd_bias, align_bias_to_signals
from backtest import RiskParams, run_backtest, compute_metrics


def analyse_pair(pair: str, interval: str, period: str, htf: str,
                 ribbon_p: RibbonParams, risk_p: RiskParams,
                 macro_p: MacroParams, macro_df: pd.DataFrame) -> list[dict]:
    print(f"\n=== {pair}  ({interval}, {period}, HTF={htf}) ===")
    px = dp.fetch_price(pair, interval=interval, period=period)
    px = dp.attach_htf_shield(px, htf_rule=htf,
                              ema_fast=ribbon_p.ma1_length, ema_slow=ribbon_p.ma2_length)
    sig = compute_signals(px, ribbon_p)
    n_long = int(sig["bull_dot"].sum())
    n_short = int(sig["bear_dot"].sum())
    print(f"  signal bars: {len(sig)} | raw dots -> long {n_long}, short {n_short} "
          f"| {sig.index.min().date()} -> {sig.index.max().date()}")

    usd_bias = compute_usd_bias(macro_df, macro_p)
    bias_series = align_bias_to_signals(sig.index, usd_bias)

    rows = []
    # Baseline: Layer 1 only
    base_trades = run_backtest(sig, pair, risk_p, usd_bias_series=None, macro_p=macro_p)
    base_m = compute_metrics(base_trades, risk_p.risk_per_trade)
    base_m["mode"], base_m["pair"] = "L1 only", pair
    rows.append(base_m)

    # Filtered: Layer 1 + Layer 2 (Weight of the Dollar)
    filt_trades = run_backtest(sig, pair, risk_p, usd_bias_series=bias_series, macro_p=macro_p)
    filt_m = compute_metrics(filt_trades, risk_p.risk_per_trade)
    filt_m["mode"], filt_m["pair"] = "L1 + DXY", pair
    rows.append(filt_m)
    return rows


def main():
    ap = argparse.ArgumentParser(description="FV Ribbon backtester (Layer1 vs Layer1+DXY)")
    ap.add_argument("--pairs", nargs="+", default=["GBPUSD=X", "AUDUSD=X"])
    ap.add_argument("--interval", default="1h", help="1h (default), 1d, 15m ...")
    ap.add_argument("--period", default="730d", help="yfinance period, e.g. 730d, 10y")
    ap.add_argument("--htf", default="4h", help="higher-timeframe shield rule")
    ap.add_argument("--rr", type=float, default=1.5, help="reward:risk target")
    ap.add_argument("--atr-mult", type=float, default=1.5, help="stop = ATR x this")
    ap.add_argument("--lookback", type=int, default=20, help="macro trend lookback (days)")
    ap.add_argument("--no-neutral", action="store_true",
                    help="block trades when USD regime is neutral (default: allow)")
    ap.add_argument("--no-disarm-exit", action="store_true",
                    help="disable 'exit when ribbon disarms'")
    args = ap.parse_args()

    ribbon_p = RibbonParams()
    risk_p = RiskParams(atr_sl_mult=args.atr_mult, rr_target=args.rr,
                        exit_on_disarm=not args.no_disarm_exit)
    macro_p = MacroParams(lookback_days=args.lookback, allow_neutral=not args.no_neutral)

    print("Fetching FRED macro (DXY proxy + Treasury yields, no key)...")
    try:
        macro_df = dp.fetch_macro()
        print(f"  macro: {macro_df.shape[0]} daily rows, "
              f"{macro_df.index.min().date()} -> {macro_df.index.max().date()}")
    except Exception as e:
        print(f"  [WARN] macro fetch failed ({e}); DXY filter will be neutral.")
        macro_df = pd.DataFrame(columns=["dxy", "y10", "y2"])

    all_rows = []
    for pair in args.pairs:
        try:
            all_rows.extend(analyse_pair(pair, args.interval, args.period, args.htf,
                                         ribbon_p, risk_p, macro_p, macro_df))
        except Exception as e:
            print(f"  [ERROR] {pair}: {e}", file=sys.stderr)

    if not all_rows:
        print("No results. Check connectivity / symbols.")
        return

    cols = ["pair", "mode", "trades", "win_rate", "profit_factor",
            "expectancy_R", "total_R", "return_pct", "max_drawdown_pct"]
    table = [[r.get(c, "") for c in cols] for r in all_rows]
    print("\n" + "=" * 78)
    print("RESULTS — Layer 1 (raw) vs Layer 1 + DXY 'Weight of the Dollar' filter")
    print("=" * 78)
    print(tabulate(table, headers=cols, tablefmt="github"))
    print("\nRead: filter EARNS its place only if it lifts profit_factor / expectancy_R")
    print("and/or cuts max_drawdown_pct WITHOUT collapsing the trade count to noise.")


if __name__ == "__main__":
    main()
