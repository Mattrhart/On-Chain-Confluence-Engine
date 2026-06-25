"""
sharpe_hunt.py — find configs with Sharpe >= 2.0 and >= 75 trades/year per asset.

Constraints: min 150 trades / 730d, target Sharpe >= 2.0 (accept >= 1.5 if volume high).
"""

from __future__ import annotations
import itertools
import data_providers as dp
from fv_ribbon import RibbonParams, compute_signals
from macro_filter import MacroParams, align_strength_to_signals, load_macro_strength
from backtest import RiskParams, run_backtest, compute_metrics

HTF = (20, 50)
MIN_TRADES = 150  # ~75/year
MIN_SHARPE_TARGET = 2.0
MIN_SHARPE_FLOOR = 1.5

ASSETS = {
    "ETH-USD":  {"pmi": "ism",  "dir": False, "fast": 10, "slow": 70},
    "AUDUSD=X": {"pmi": "oecd", "dir": True,  "fast": 30, "slow": 80},
    "NZDUSD=X": {"pmi": "oecd", "dir": True,  "fast": 15, "slow": 60},
    "USDCHF=X": {"pmi": "ism",  "dir": True,  "fast": 10, "slow": 50},
}

macro = {k: load_macro_strength(k) for k in ("oecd", "ism")}


def eval_cfg(pair, base, ang, max_d, rocket, htf_align, rr, nn, min_usd):
    rp = RibbonParams(
        ma1_length=base["fast"], ma2_length=base["slow"],
        use_sigma_angle=True, angle_thresh_deg=float(ang),
        angle_directional=base["dir"],
        max_retest_dots=max_d, fire_rocket_dot=rocket,
        require_htf_align=htf_align,
    )
    px = dp.attach_htf_shield(dp.fetch_price(pair, "1h", "730d"), "4h", *HTF)
    sig = compute_signals(px, rp)
    strength = align_strength_to_signals(sig.index, macro[base["pmi"]])
    if min_usd > 0:
        strength = strength.where(strength.abs() >= min_usd, 0)
    m = compute_metrics(
        run_backtest(sig, pair, RiskParams(1.5, rr), strength, MacroParams(not nn)))
    return m


def hunt_pair(pair, base):
    best = None
    candidates = []
    for ang, max_d, rocket, htf, rr, nn, min_usd in itertools.product(
            [6, 7, 8, 9, 10, 12],
            [1, 2, 3],
            [False, True],
            [False, True],
            [1.5, 2.0, 3.0],
            [True, False],
            [0, 3, 5],
    ):
        m = eval_cfg(pair, base, ang, max_d, rocket, htf, rr, nn, min_usd)
        t, s = m["trades"], m["sharpe_ratio"]
        if not isinstance(s, (int, float)) or t < MIN_TRADES:
            continue
        if s < MIN_SHARPE_FLOOR:
            continue
        row = dict(ang=ang, max_d=max_d, rocket=rocket, htf=htf, rr=rr, nn=nn,
                   min_usd=min_usd, **m)
        candidates.append(row)
        if s >= MIN_SHARPE_TARGET and (best is None or s > best["sharpe_ratio"]):
            best = row

    if best is None and candidates:
        candidates.sort(key=lambda r: (r["sharpe_ratio"], r["trades"]), reverse=True)
        best = candidates[0]
    return best, len(candidates)


print("Sharpe hunt (min 150 trades / 730d)\n")
results = {}
for pair, base in ASSETS.items():
    best, n = hunt_pair(pair, base)
    sym = pair.replace("=X", "").replace("-USD", "USD")
    if best:
        results[sym] = best
        print(f"{sym}: Sharpe={best['sharpe_ratio']:.2f} trades={best['trades']} PF={best['profit_factor']:.2f} "
              f"ang={best['ang']} max={best['max_d']} rocket={best['rocket']} htf={best['htf']} "
              f"rr={best['rr']} nn={best['nn']} min_usd={best['min_usd']}  ({n} valid combos)")
    else:
        print(f"{sym}: NO config met floor (Sharpe>={MIN_SHARPE_FLOOR}, trades>={MIN_TRADES})")
