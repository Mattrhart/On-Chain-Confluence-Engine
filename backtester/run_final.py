"""
run_final.py — final stacked backtest.

Per-asset Layer 1 gates (asset_profiles) + 6-pillar macro filter (macro_pillars).

Compares:
  L1 only     — asset-specific technical gate, no macro
  L1 + Macro  — same gate + 6-pillar usd_strength filter (live main.py logic)
"""

from __future__ import annotations
import argparse
import sys
from tabulate import tabulate

import data_providers as dp
from asset_profiles import FINAL_UNIVERSE, resolve_profile
from fv_ribbon import compute_signals
from macro_filter import MacroParams, align_strength_to_signals, load_macro_strength
from backtest import RiskParams, run_backtest, compute_metrics


def analyse_pair(pair: str, interval: str, period: str, htf: str,
                 risk_p: RiskParams, macro_p: MacroParams,
                 macro_df) -> list[dict]:
    profile_name, ribbon_p = resolve_profile(pair)
    print(f"\n=== {pair}  profile={profile_name}  ({interval}, {period}) ===")

    px = dp.fetch_price(pair, interval=interval, period=period)
    px = dp.attach_htf_shield(px, htf_rule=htf,
                              ema_fast=ribbon_p.ma1_length, ema_slow=ribbon_p.ma2_length)
    sig = compute_signals(px, ribbon_p)
    n_long = int(sig["bull_dot"].sum())
    n_short = int(sig["bear_dot"].sum())
    print(f"  bars={len(sig)} dots L{n_long}/S{n_short} | "
          f"{sig.index.min().date()} -> {sig.index.max().date()}")

    strength = align_strength_to_signals(sig.index, macro_df)
    rows = []

    for mode, strength_series in [("L1 only", None), ("L1 + 6-Pillar", strength)]:
        trades = run_backtest(sig, pair, risk_p,
                              usd_strength_series=strength_series, macro_p=macro_p)
        m = compute_metrics(trades, risk_p.risk_per_trade)
        m.update({"pair": pair, "profile": profile_name, "mode": mode})
        rows.append(m)
    return rows


def main():
    ap = argparse.ArgumentParser(description="Final stacked backtest (asset gates + 6-pillar macro)")
    ap.add_argument("--pairs", nargs="+", default=FINAL_UNIVERSE)
    ap.add_argument("--interval", default="1h")
    ap.add_argument("--period", default="730d")
    ap.add_argument("--htf", default="4h")
    ap.add_argument("--rr", type=float, default=1.5)
    ap.add_argument("--atr-mult", type=float, default=1.5)
    ap.add_argument("--no-neutral", action="store_true",
                    help="block trades when usd_strength yields neutral bias (0)")
    ap.add_argument("--disarm-exit", action="store_true",
                    help="Exit open trades when ribbon disarms (legacy; default is hold to stop/target)")
    args = ap.parse_args()

    risk_p = RiskParams(atr_sl_mult=args.atr_mult, rr_target=args.rr,
                        exit_on_disarm=args.disarm_exit)
    macro_p = MacroParams(allow_neutral=not args.no_neutral)

    print("Building 6-pillar macro (FRED, publication-lag adjusted)...")
    try:
        macro_df = load_macro_strength()
        latest = macro_df["usd_strength"].dropna().iloc[-1]
        print(f"  macro rows={macro_df.shape[0]} | latest usd_strength={int(latest):+d} "
              f"({macro_df['market_state'].iloc[-1]})")
    except Exception as e:
        print(f"  [FATAL] macro build failed: {e}", file=sys.stderr)
        sys.exit(1)

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
    print("\n" + "=" * 90)
    print("FINAL RESULTS — asset-specific Layer 1 + 6-pillar macro stack")
    print("=" * 90)
    print(tabulate(table, headers=cols, tablefmt="github"))


if __name__ == "__main__":
    main()
