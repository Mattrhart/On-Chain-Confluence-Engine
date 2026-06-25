"""
optimize.py — hyperparameter optimization harness for the FV Ribbon stack.

Systematically sweeps Layer 1 (MA lengths, sigma angle), risk (ATR RR targets),
and Layer 2 (macro PMI source, no-neutral enforcement) per asset, maximizing
annualized Sharpe ratio (tie-break: profit factor).

Does NOT touch live app/main.py.
"""

from __future__ import annotations

import argparse
import itertools
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass

import pandas as pd
from tabulate import tabulate

import data_providers as dp
from asset_profiles import FINAL_UNIVERSE, resolve_profile
from fv_ribbon import RibbonParams, compute_signals
from macro_filter import MacroParams, align_strength_to_signals, load_macro_strength
from backtest import RiskParams, run_backtest, compute_metrics

# HTF shield stays fixed at Pine 4H 20/50 regardless of chart MA sweep
HTF_EMA_FAST = 20
HTF_EMA_SLOW = 50

FAST_EMA_RANGE = range(10, 31, 5)       # 10, 15, 20, 25, 30
SLOW_SMA_RANGE = range(40, 101, 10)     # 40 .. 100
ANGLE_RANGE = range(4, 13)              # 4° .. 12°
RR_TARGETS = (1.5, 2.0, 3.0)
PMI_SOURCES = ("oecd", "ism")
ATR_SL_MULT = 1.5
MIN_TRADES = 15


@dataclass(frozen=True)
class Combo:
    pair: str
    fast_ema: int
    slow_sma: int
    angle_deg: int | None
    rr_target: float
    pmi_source: str
    no_neutral: bool


@dataclass
class EvalResult:
    combo: Combo
    sharpe_ratio: float
    profit_factor: float
    win_rate: float
    trades: int
    return_pct: float
    max_drawdown_pct: float
    expectancy_R: float


# Worker globals (populated by pool initializer)
_W_PX: dict[str, pd.DataFrame] = {}
_W_MACRO: dict[str, pd.DataFrame] = {}
_W_GATE: dict[str, tuple[bool, bool, float, float]] = {}  # sigma, directional, req_gap, min_slope


def _gate_template(pair: str) -> tuple[bool, bool, float, float]:
    """(use_sigma, angle_directional, req_gap, min_slope) from asset profile."""
    _, rp = resolve_profile(pair)
    return rp.use_sigma_angle, rp.angle_directional, rp.req_gap, rp.min_slope


def _build_ribbon(combo: Combo) -> RibbonParams:
    use_sigma, directional, req_gap, min_slope = _W_GATE[combo.pair]
    return RibbonParams(
        ma1_length=combo.fast_ema,
        ma2_length=combo.slow_sma,
        use_sigma_angle=use_sigma,
        angle_thresh_deg=float(combo.angle_deg) if (use_sigma and combo.angle_deg is not None) else 8.0,
        angle_directional=directional,
        req_gap=req_gap,
        min_slope=min_slope,
    )


def _eval_combo(combo: Combo) -> EvalResult:
    px = _W_PX[combo.pair]
    macro_df = _W_MACRO[combo.pmi_source]
    strength = align_strength_to_signals(px.index, macro_df)

    ribbon = _build_ribbon(combo)
    sig = compute_signals(px, ribbon)

    risk = RiskParams(atr_sl_mult=ATR_SL_MULT, rr_target=combo.rr_target)
    macro_p = MacroParams(allow_neutral=not combo.no_neutral)

    trades = run_backtest(sig, combo.pair, risk,
                          usd_strength_series=strength, macro_p=macro_p)
    m = compute_metrics(trades, risk.risk_per_trade)

    sharpe = m["sharpe_ratio"]
    if m["trades"] < MIN_TRADES or not isinstance(sharpe, (int, float)) or sharpe != sharpe:
        sharpe = float("-inf")

    return EvalResult(
        combo=combo,
        sharpe_ratio=sharpe,
        profit_factor=m["profit_factor"],
        win_rate=m["win_rate"],
        trades=m["trades"],
        return_pct=m["return_pct"],
        max_drawdown_pct=m["max_drawdown_pct"],
        expectancy_R=m["expectancy_R"],
    )


def _init_worker(px_cache: dict, macro_cache: dict, gate_cache: dict):
    global _W_PX, _W_MACRO, _W_GATE
    _W_PX = px_cache
    _W_MACRO = macro_cache
    _W_GATE = gate_cache


def _combo_grid(pairs: list[str], quick: bool) -> list[Combo]:
    fast = [15, 20, 25] if quick else list(FAST_EMA_RANGE)
    slow = [50, 70, 90] if quick else list(SLOW_SMA_RANGE)
    angles = [6, 8, 10] if quick else list(ANGLE_RANGE)
    rr = [1.5, 2.0] if quick else list(RR_TARGETS)
    pmi = ["oecd"] if quick else list(PMI_SOURCES)
    neutral_flags = [False, True] if not quick else [True, False]

    combos: list[Combo] = []
    for pair in pairs:
        use_sigma, _, _, _ = _gate_template(pair)
        angle_vals: list[int | None] = angles if use_sigma else [None]
        for fe, ss, ang, rr_t, pmi_s, nn in itertools.product(
                fast, slow, angle_vals, rr, pmi, neutral_flags):
            if fe >= ss:
                continue
            combos.append(Combo(pair, fe, ss, ang, rr_t, pmi_s, nn))
    return combos


def _preload(pairs: list[str], interval: str, period: str, htf: str,
             pmi_sources: tuple[str, ...]) -> tuple[dict, dict, dict]:
    px_cache: dict[str, pd.DataFrame] = {}
    gate_cache: dict[str, tuple] = {}

    print("Pre-loading price + HTF shield (fixed 4H 20/50)...")
    for pair in pairs:
        raw = dp.fetch_price(pair, interval=interval, period=period)
        px_cache[pair] = dp.attach_htf_shield(
            raw, htf_rule=htf, ema_fast=HTF_EMA_FAST, ema_slow=HTF_EMA_SLOW)
        gate_cache[pair] = _gate_template(pair)
        print(f"  {pair}: {len(px_cache[pair])} bars")

    print("Pre-loading macro pillars...")
    macro_cache: dict[str, pd.DataFrame] = {}
    for src in pmi_sources:
        macro_cache[src] = load_macro_strength(pmi_source=src)
        latest = int(macro_cache[src]["usd_strength"].dropna().iloc[-1])
        print(f"  pmi={src}: rows={len(macro_cache[src])} latest usd_strength={latest:+d}")

    return px_cache, macro_cache, gate_cache


def _rank_key(r: EvalResult) -> tuple:
    pf = r.profit_factor if isinstance(r.profit_factor, (int, float)) else 0.0
    if pf == float("inf"):
        pf = 99.0
    return (r.sharpe_ratio, pf)


def optimize(pairs: list[str], interval: str, period: str, htf: str,
             jobs: int, quick: bool) -> list[EvalResult]:
    pmi_sources = ("oecd",) if quick else PMI_SOURCES
    px_cache, macro_cache, gate_cache = _preload(pairs, interval, period, htf, pmi_sources)
    combos = _combo_grid(pairs, quick)
    total = len(combos)
    print(f"\nGrid size: {total} combinations ({jobs} workers)\n")

    best_by_pair: dict[str, EvalResult] = {}
    t0 = time.time()

    if jobs <= 1:
        _init_worker(px_cache, macro_cache, gate_cache)
        for i, combo in enumerate(combos, 1):
            res = _eval_combo(combo)
            prev = best_by_pair.get(combo.pair)
            if prev is None or _rank_key(res) > _rank_key(prev):
                best_by_pair[combo.pair] = res
            if i % 200 == 0 or i == total:
                elapsed = time.time() - t0
                print(f"  [{i}/{total}] {elapsed:.0f}s elapsed...")
    else:
        done = 0
        with ProcessPoolExecutor(max_workers=jobs,
                                 initializer=_init_worker,
                                 initargs=(px_cache, macro_cache, gate_cache)) as pool:
            futures = {pool.submit(_eval_combo, c): c for c in combos}
            for fut in as_completed(futures):
                res = fut.result()
                prev = best_by_pair.get(res.combo.pair)
                if prev is None or _rank_key(res) > _rank_key(prev):
                    best_by_pair[res.combo.pair] = res
                done += 1
                if done % 500 == 0 or done == total:
                    print(f"  [{done}/{total}] {time.time() - t0:.0f}s elapsed...")

    print(f"\nOptimization finished in {time.time() - t0:.1f}s")
    return [best_by_pair[p] for p in pairs if p in best_by_pair]


def _print_results(results: list[EvalResult]):
    rows = []
    for r in results:
        c = r.combo
        ang = f"{c.angle_deg}°" if c.angle_deg is not None else "chop"
        rows.append([
            c.pair,
            r.sharpe_ratio,
            r.profit_factor,
            r.win_rate,
            r.trades,
            r.return_pct,
            r.max_drawdown_pct,
            c.fast_ema,
            c.slow_sma,
            ang,
            c.rr_target,
            c.pmi_source,
            "yes" if c.no_neutral else "no",
        ])

    headers = [
        "asset", "sharpe", "PF", "win%", "trades", "return%", "maxDD%",
        "fast_ema", "slow_sma", "angle", "RR", "pmi", "no_neutral",
    ]
    print("\n" + "=" * 100)
    print("BEST PARAMETER COMBINATION PER ASSET (max Sharpe, tie-break PF)")
    print("=" * 100)
    print(tabulate(rows, headers=headers, tablefmt="github", floatfmt=".2f"))


def main():
    ap = argparse.ArgumentParser(description="Hyperparameter optimizer (Sharpe + PF)")
    ap.add_argument("--pairs", nargs="+", default=FINAL_UNIVERSE)
    ap.add_argument("--interval", default="1h")
    ap.add_argument("--period", default="730d")
    ap.add_argument("--htf", default="4h")
    ap.add_argument("--jobs", type=int, default=max(1, (__import__("os").cpu_count() or 4) - 1),
                    help="parallel workers (1 = serial)")
    ap.add_argument("--quick", action="store_true", help="reduced grid for smoke test")
    args = ap.parse_args()

    try:
        results = optimize(args.pairs, args.interval, args.period, args.htf,
                           args.jobs, args.quick)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"[FATAL] {e}", file=sys.stderr)
        sys.exit(1)

    if not results:
        print("No results.")
        return
    _print_results(results)


if __name__ == "__main__":
    main()
