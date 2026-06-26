"""
baseline_universe_scan.py — compare universal MAIN baseline across forex + monitored assets.

Uses strategy_main.pine defaults (RibbonParams()): EMA20/SMA50, 1 retest dot, RR 1.5.
All metrics are POST-macro filter (trades blocked by Layer 2 are excluded from Sharpe).

Usage:
  python baseline_universe_scan.py
  python baseline_universe_scan.py --interval 15m --period 60d
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import data_providers as dp
from backtest import RiskParams, compute_metrics, run_backtest
from fv_ribbon import RibbonParams, compute_signals
from macro_filter import MacroParams, align_strength_to_signals, load_macro_strength

# Mirror app/trading_config.py (import when available)
try:
    from app.trading_config import ASSET_MACRO, DEFAULT_MACRO
except ImportError:
    ASSET_MACRO = {
        "ETHUSD": {"pmi_source": "ism", "require_non_neutral": False},
        "AUDUSD": {"pmi_source": "oecd", "require_non_neutral": False},
        "NZDUSD": {"pmi_source": "oecd", "require_non_neutral": True},
        "USDJPY": {"pmi_source": "ism", "require_non_neutral": False},
        "USDCHF": {"pmi_source": "ism", "require_non_neutral": False},
        "EURUSD": {"pmi_source": "ism", "require_non_neutral": False},
        "GBPUSD": {"pmi_source": "ism", "require_non_neutral": False},
    }
    DEFAULT_MACRO = {"pmi_source": "oecd", "require_non_neutral": False}

BASELINE = RibbonParams()
RISK = RiskParams(1.5, 1.5)

FOREX = [
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X", "AUDUSD=X", "NZDUSD=X", "USDCAD=X",
    "EURJPY=X", "GBPJPY=X", "EURGBP=X", "AUDJPY=X", "EURAUD=X", "EURCHF=X", "GBPCHF=X",
    "CADJPY=X", "NZDJPY=X", "AUDCAD=X", "AUDNZD=X", "EURNZD=X", "GBPAUD=X", "GBPNZD=X",
    "GBPCAD=X", "EURCAD=X", "CHFJPY=X", "AUDCHF=X", "NZDCAD=X", "NZDCHF=X",
]

CRYPTO = [("BTC-USD", "BTCUSD"), ("SOL-USD", "SOLUSD"), ("ETH-USD", "ETHUSD")]
NDX = [("^NDX", "NDX100"), ("NQ=F", "NQ100")]
HYPE_CANDIDATES = ["HYPE-USD", "HYPEUSDT-USD", "HYPE-USDT", "HYPER-USD"]


def macro_cfg(sym: str) -> dict:
    s = sym.upper().replace("=X", "").replace("-", "")
    return ASSET_MACRO.get(s, DEFAULT_MACRO)


def normalize_sym(yf_sym: str, label: str) -> str:
    return label.upper().replace("=X", "").replace("-USD", "USD").replace("-", "")


def run_one(yf_sym: str, label: str, interval: str, period: str, macro_cache: dict):
    try:
        px = dp.attach_htf_shield(
            dp.fetch_price(yf_sym, interval, period), "4h", 20, 50)
    except Exception as e:
        return None, str(e)
    if len(px) < 200:
        return None, f"insufficient bars ({len(px)})"

    sym = normalize_sym(yf_sym, label)
    mc = macro_cfg(sym)
    pmi = mc["pmi_source"]
    if pmi not in macro_cache:
        macro_cache[pmi] = load_macro_strength(pmi)

    sig = compute_signals(px, BASELINE)
    strength = align_strength_to_signals(sig.index, macro_cache[pmi])
    macro_p = MacroParams(not mc["require_non_neutral"])
    trades = run_backtest(sig, sym, RISK, strength, macro_p)
    m = compute_metrics(trades)
    days = max((sig.index[-1] - sig.index[0]).days, 1)
    return {
        "symbol": label.replace("=X", ""),
        "trades": m["trades"],
        "sharpe": m["sharpe_ratio"],
        "pf": m["profit_factor"],
        "wr": m["win_rate"],
        "total_r": m["total_R"],
        "max_dd": m["max_drawdown_pct"],
        "yr": round(m["trades"] / days * 365),
        "pmi": pmi,
    }, None


def main():
    ap = argparse.ArgumentParser(description="Universal MAIN baseline universe scan")
    ap.add_argument("--interval", default="15m")
    ap.add_argument("--period", default="60d")
    args = ap.parse_args()

    macro_cache: dict = {}
    rows: list[dict] = []
    errors: list[tuple[str, str]] = []

    for f in FOREX:
        r, err = run_one(f, f.replace("=X", ""), args.interval, args.period, macro_cache)
        if r:
            rows.append(r)
        else:
            errors.append((f, err or "unknown"))

    for yf, label in CRYPTO:
        r, err = run_one(yf, label, args.interval, args.period, macro_cache)
        if r:
            rows.append(r)
        else:
            errors.append((label, err or "unknown"))

    for yf in HYPE_CANDIDATES:
        r, err = run_one(yf, "HYPEUSD", args.interval, args.period, macro_cache)
        if r:
            rows.append(r)
            break
    else:
        errors.append(("HYPEUSD", "no yfinance symbol found"))

    for yf, label in NDX:
        r, err = run_one(yf, label, args.interval, args.period, macro_cache)
        if r:
            rows.append(r)
            break
    else:
        errors.append(("NDX100", "no index data"))

    rows.sort(key=lambda x: x["sharpe"], reverse=True)

    print("=" * 90)
    print(f"UNIVERSAL BASELINE — POST-MACRO — {args.period} {args.interval}")
    print("EMA20/SMA50 | 1 retest dot | RR 1.5 | Layer 2 macro filter ON")
    print("=" * 90)
    print(f"{'#':>3} {'Symbol':<10} {'Trades':>6} {'~Yr':>5} {'Sharpe':>7} {'PF':>5} {'WR%':>5} {'TotR':>7} {'MaxDD%':>7}")
    print("-" * 90)
    for i, r in enumerate(rows, 1):
        print(f"{i:>3} {r['symbol']:<10} {r['trades']:>6} {r['yr']:>5} {r['sharpe']:>7.2f} "
              f"{r['pf']:>5.2f} {r['wr']:>5.1f} {r['total_r']:>7.2f} {r['max_dd']:>7.1f}")

    if rows:
        print(f"\nBEST:  {rows[0]['symbol']}  Sharpe {rows[0]['sharpe']:.2f}")
        print(f"WORST: {rows[-1]['symbol']}  Sharpe {rows[-1]['sharpe']:.2f}")
        viable = [r for r in rows if r["trades"] >= 15]
        if viable:
            print(f"MEDIAN Sharpe (>=15 trades, n={len(viable)}): "
                  f"{statistics.median([r['sharpe'] for r in viable]):.2f}")

    if errors:
        print("\nSkipped:")
        for sym, err in errors:
            print(f"  {sym}: {err}")


if __name__ == "__main__":
    main()
