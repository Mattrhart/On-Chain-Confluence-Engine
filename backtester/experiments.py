"""
experiments.py — test win-rate hypotheses on the FV Ribbon, measurably.

Hypotheses under test (the user's own diagnosis):
  H1 "background needs to align" -> require_htf_align (kill counter-trend dots)
  H2 "firing during chop"        -> stronger chop gate (higher req_gap / min_slope)
  H3 combine H1 + H2

For each pair we print L1-only metrics per config so the WIN RATE delta is visible.
"""

from __future__ import annotations
import pandas as pd
from tabulate import tabulate

import data_providers as dp
from fv_ribbon import RibbonParams, compute_signals
from backtest import RiskParams, run_backtest, compute_metrics

PAIRS = ["ETH-USD", "AUDUSD=X", "USDJPY=X", "NZDUSD=X"]
INTERVAL, PERIOD, HTF = "1h", "730d", "4h"

CONFIGS = {
    "baseline":        RibbonParams(),
    "chop_strong":     RibbonParams(req_gap=1.0, min_slope=0.06),
    "sigma_ang_6":     RibbonParams(use_sigma_angle=True, angle_thresh_deg=6.0),
    "sigma_ang_10":    RibbonParams(use_sigma_angle=True, angle_thresh_deg=10.0),
    "sigma_ang_15":    RibbonParams(use_sigma_angle=True, angle_thresh_deg=15.0),
    "sigma_ang_dir":   RibbonParams(use_sigma_angle=True, angle_thresh_deg=10.0, angle_directional=True),
}

RISK = RiskParams(atr_sl_mult=1.5, rr_target=1.5)


def main():
    rows = []
    for pair in PAIRS:
        px = dp.fetch_price(pair, interval=INTERVAL, period=PERIOD)
        px = dp.attach_htf_shield(px, htf_rule=HTF)
        for name, rp in CONFIGS.items():
            sig = compute_signals(px, rp)
            trades = run_backtest(sig, pair, RISK, usd_bias_series=None)
            m = compute_metrics(trades, RISK.risk_per_trade)
            rows.append({"pair": pair, "config": name, "trades": m["trades"],
                         "win%": m["win_rate"], "PF": m["profit_factor"],
                         "exp_R": m["expectancy_R"], "ret%": m["return_pct"],
                         "maxDD%": m["max_drawdown_pct"]})

    cols = ["pair", "config", "trades", "win%", "PF", "exp_R", "ret%", "maxDD%"]
    table = [[r[c] for c in cols] for r in rows]
    print("\nWIN-RATE EXPERIMENTS (Layer 1 only, RR=1.5 => ~40% breakeven win rate)")
    print(tabulate(table, headers=cols, tablefmt="github"))


if __name__ == "__main__":
    main()
