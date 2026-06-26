"""
run.py — FV Ribbon backtester harness (legacy / generic pairs).

Uses asset_profiles when a symbol is in the registry; otherwise baseline Layer 1.
Macro filter: 6-pillar usd_strength (macro_pillars), not the old DXY proxy.
"""

from __future__ import annotations
import argparse
import sys
import pandas as pd
from tabulate import tabulate

import data_providers as dp
from asset_profiles import resolve_profile
from fv_ribbon import compute_signals
from macro_filter import MacroParams, align_strength_to_signals, load_macro_strength
from backtest import RiskParams, run_backtest, compute_metrics


def analyse_pair(pair: str, interval: str, period: str, htf: str,
                 risk_p: RiskParams, macro_p: MacroParams,
                 macro_df: pd.DataFrame) -> list[dict]:
    profile_name, ribbon_p = resolve_profile(pair)
    print(f"\n=== {pair}  profile={profile_name}  ({interval}, {period}, HTF={htf}) ===")
    px = dp.fetch_price(pair, interval=interval, period=period)
    px = dp.attach_htf_shield(px, htf_rule=htf,
                              ema_fast=ribbon_p.ma1_length, ema_slow=ribbon_p.ma2_length)
    sig = compute_signals(px, ribbon_p)
    n_long = int(sig["bull_dot"].sum())
    n_short = int(sig["bear_dot"].sum())
    print(f"  signal bars: {len(sig)} | dots L{n_long}/S{n_short} "
          f"| {sig.index.min().date()} -> {sig.index.max().date()}")

    strength = align_strength_to_signals(sig.index, macro_df)
    rows = []
    base_trades = run_backtest(sig, pair, risk_p, usd_strength_series=None, macro_p=macro_p)
    base_m = compute_metrics(base_trades, risk_p.risk_per_trade)
    base_m.update({"mode": "L1 only", "pair": pair, "profile": profile_name})
    rows.append(base_m)

    filt_trades = run_backtest(sig, pair, risk_p, usd_strength_series=strength, macro_p=macro_p)
    filt_m = compute_metrics(filt_trades, risk_p.risk_per_trade)
    filt_m.update({"mode": "L1 + 6-Pillar", "pair": pair, "profile": profile_name})
    rows.append(filt_m)
    return rows


def main():
    ap = argparse.ArgumentParser(description="FV Ribbon backtester (Layer1 vs Layer1+6-Pillar)")
    ap.add_argument("--pairs", nargs="+", default=["GBPUSD=X", "AUDUSD=X"])
    ap.add_argument("--interval", default="1h")
    ap.add_argument("--period", default="730d")
    ap.add_argument("--htf", default="4h")
    ap.add_argument("--rr", type=float, default=1.5)
    ap.add_argument("--atr-mult", type=float, default=1.5)
    ap.add_argument("--no-neutral", action="store_true")
    ap.add_argument("--disarm-exit", action="store_true",
                    help="Exit open trades when ribbon disarms (legacy; default is hold to stop/target)")
    args = ap.parse_args()

    risk_p = RiskParams(atr_sl_mult=args.atr_mult, rr_target=args.rr,
                        exit_on_disarm=args.disarm_exit)
    macro_p = MacroParams(allow_neutral=not args.no_neutral)

    print("Building 6-pillar macro (FRED)...")
    try:
        macro_df = load_macro_strength()
        print(f"  macro: {macro_df.shape[0]} rows, "
              f"{macro_df.index.min().date()} -> {macro_df.index.max().date()}")
    except Exception as e:
        print(f"  [WARN] macro failed ({e}); filter disabled.")
        macro_df = pd.DataFrame({"usd_strength": []})

    all_rows = []
    for pair in args.pairs:
        try:
            all_rows.extend(analyse_pair(pair, args.interval, args.period, args.htf,
                                         risk_p, macro_p, macro_df))
        except Exception as e:
            print(f"  [ERROR] {pair}: {e}", file=sys.stderr)

    if not all_rows:
        print("No results.")
        return

    cols = ["pair", "profile", "mode", "trades", "win_rate", "profit_factor",
            "expectancy_R", "total_R", "return_pct", "max_drawdown_pct"]
    table = [[r.get(c, "") for c in cols] for r in all_rows]
    print("\n" + "=" * 78)
    print("RESULTS — asset Layer 1 vs Layer 1 + 6-pillar macro")
    print("=" * 78)
    print(tabulate(table, headers=cols, tablefmt="github"))


if __name__ == "__main__":
    main()
