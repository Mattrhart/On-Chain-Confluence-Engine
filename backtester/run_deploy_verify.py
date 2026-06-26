"""Print deploy profile metrics (post-macro filter) for the live 15m timeframe."""

from __future__ import annotations
import data_providers as dp
from deploy_profiles import (
    DEPLOY_RIBBON, DEPLOY_MACRO, DEPLOY_UNIVERSE, DEPLOY_RR,
    DEPLOY_INTERVAL, DEPLOY_PERIOD,
)
from fv_ribbon import compute_signals
from macro_filter import MacroParams, align_strength_to_signals, load_macro_strength
from backtest import RiskParams, run_backtest, compute_metrics

macro = {k: load_macro_strength(k) for k in ("oecd", "ism")}
print(f"Institutional V4 — {DEPLOY_PERIOD} {DEPLOY_INTERVAL} — trades AFTER macro filter\n")
total = 0
for pair in DEPLOY_UNIVERSE:
    rp = DEPLOY_RIBBON[pair]
    sym = pair.replace("=X", "").replace("-USD", "USD")
    mc = DEPLOY_MACRO[sym]
    px = dp.attach_htf_shield(
        dp.fetch_price(pair, DEPLOY_INTERVAL, DEPLOY_PERIOD), "4h", 20, 50)
    sig = compute_signals(px, rp)
    dots = int(sig.bull_dot.sum() + sig.bear_dot.sum())
    strength = align_strength_to_signals(sig.index, macro[mc["pmi_source"]])
    rr = DEPLOY_RR.get(sym, 1.5)
    m = compute_metrics(
        run_backtest(sig, pair, RiskParams(1.5, rr), strength, MacroParams(not mc["require_non_neutral"])))
    total += m["trades"]
    days = max((sig.index[-1] - sig.index[0]).days, 1)
    yr = m["trades"] / days * 365
    print(f"{sym:<8} dots={dots:>4}  trades={m['trades']:>4}  (~{yr:.0f}/yr)  "
          f"PF={m['profit_factor']:.2f}  Sharpe={m['sharpe_ratio']:.2f}")
print(f"\nPortfolio total: {total} trades / {DEPLOY_PERIOD} (~{total/days*365:.0f}/yr projected)")
