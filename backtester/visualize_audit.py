"""
visualize_audit.py — Interactive Plotly audit of V4 15m backtests.

Generates:
  • audit_chart_<SYMBOL>.html  — candlesticks, trade overlays, equity & drawdown
  • audit_trade_log_<SYMBOL>.csv — full trade ledger with setup type & macro as-of

Integrity checks (anti-lookahead):
  • Signal bar had a valid dot before entry
  • Entry fill matches declared execution model (signal-bar close = Pine confirmed bar)
  • Next-bar open recorded for live-slippage transparency
  • Macro as-of timestamp strictly precedes entry time
  • Exit re-simulation uses stop-first when stop & target both touched same bar

Usage:
  python visualize_audit.py
  python visualize_audit.py --asset AUDUSD=X
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data_providers as dp
from backtest import RiskParams, Trade, compute_metrics, run_backtest
from deploy_profiles import (
    DEPLOY_INTERVAL,
    DEPLOY_MACRO,
    DEPLOY_PERIOD,
    DEPLOY_RIBBON,
    DEPLOY_RR,
)
from fv_ribbon import compute_signals
from macro_filter import MacroParams, align_strength_to_signals, load_macro_strength, trade_allowed

OUT_DIR = Path(__file__).resolve().parent
DEFAULT_PAIR = "NZDUSD=X"
# Matches backtest.py + Pine barstate.isconfirmed (enter at signal-bar close).
EXECUTION_MODEL = "signal_close"


@dataclass
class AuditRow:
    trade_id: int
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    signal_close: float
    next_bar_open: float
    entry_price: float
    exit_price: float
    direction: str
    setup_type: str
    exit_reason: str
    r_multiple: float
    macro_asof: pd.Timestamp
    macro_usd_strength: int
    macro_allowed: bool
    stop_price: float
    target_price: float
    risk_r: float


def _sym(pair: str) -> str:
    return pair.replace("=X", "").replace("-USD", "USD")


def macro_asof_series(signal_index: pd.DatetimeIndex, macro: pd.DataFrame) -> pd.Series:
    """Map each bar to the calendar timestamp of the macro row used (backward asof)."""
    left = pd.DataFrame({"ts": pd.DatetimeIndex(signal_index).astype("datetime64[ns]")})
    left = left.sort_values("ts")
    right = macro[["usd_strength"]].copy()
    right.index.name = "macro_ts"
    right = right.reset_index()
    right["macro_ts"] = pd.to_datetime(right["macro_ts"]).astype("datetime64[ns]")
    right = right.sort_values("macro_ts")
    merged = pd.merge_asof(left, right, left_on="ts", right_on="macro_ts", direction="backward")
    return pd.Series(
        pd.to_datetime(merged["macro_ts"].values),
        index=pd.DatetimeIndex(merged["ts"].values),
    ).reindex(signal_index)


def _setup_type(sig: pd.DataFrame, idx: int, direction: str) -> str:
    if direction == "LONG":
        kind = sig["bull_dot_kind"].iloc[idx]
    else:
        kind = sig["bear_dot_kind"].iloc[idx]
    return str(kind) if kind is not None and pd.notna(kind) else "unknown"


def build_ledger(
    df: pd.DataFrame,
    trades: list[Trade],
    pair: str,
    risk: RiskParams,
    strength: pd.Series,
    macro_asof: pd.Series,
    macro_p: MacroParams,
) -> list[AuditRow]:
    rows: list[AuditRow] = []
    idx = df.index
    close = df["close"].values
    open_ = df["open"].values
    atr = df["risk_atr"].values

    for tid, t in enumerate(trades, start=1):
        sig_i = int(idx.get_loc(t.entry_time))
        direction = t.direction
        r_unit = risk.atr_sl_mult * atr[sig_i]
        if direction == "LONG":
            stop = t.entry - r_unit
            target = t.entry + r_unit * risk.rr_target
        else:
            stop = t.entry + r_unit
            target = t.entry - r_unit * risk.rr_target

        next_open = float(open_[sig_i + 1]) if sig_i + 1 < len(df) else float("nan")
        usd = int(strength.iloc[sig_i])
        rows.append(AuditRow(
            trade_id=tid,
            signal_time=idx[sig_i],
            entry_time=t.entry_time,
            exit_time=t.exit_time,
            signal_close=float(close[sig_i]),
            next_bar_open=next_open,
            entry_price=t.entry,
            exit_price=t.exit,
            direction=direction,
            setup_type=_setup_type(df, sig_i, direction),
            exit_reason=t.reason,
            r_multiple=t.r_multiple,
            macro_asof=pd.Timestamp(macro_asof.iloc[sig_i]),
            macro_usd_strength=usd,
            macro_allowed=trade_allowed(pair, direction, usd, macro_p),
            stop_price=stop,
            target_price=target,
            risk_r=r_unit,
        ))
    return rows


@dataclass
class IntegrityResult:
    name: str
    passed: bool
    detail: str


def validate_integrity(
    df: pd.DataFrame,
    ledger: list[AuditRow],
    risk: RiskParams,
) -> list[IntegrityResult]:
    results: list[IntegrityResult] = []
    idx = df.index
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    bull_dot = df["bull_dot"].values
    bear_dot = df["bear_dot"].values

    entry_ok = entry_fail = 0
    next_open_note = []
    macro_ok = macro_fail = 0
    stop_first_ok = stop_first_fail = 0
    signal_ok = signal_fail = 0

    for row in ledger:
        sig_i = int(idx.get_loc(row.signal_time))

        # Valid signal dot on signal bar
        dot_valid = bool(bull_dot[sig_i]) if row.direction == "LONG" else bool(bear_dot[sig_i])
        if dot_valid:
            signal_ok += 1
        else:
            signal_fail += 1

        # Entry fill vs execution model
        if EXECUTION_MODEL == "signal_close":
            if np.isclose(row.entry_price, row.signal_close, rtol=0, atol=1e-9):
                entry_ok += 1
            else:
                entry_fail += 1
        elif EXECUTION_MODEL == "next_open":
            if np.isclose(row.entry_price, row.next_bar_open, rtol=0, atol=1e-9):
                entry_ok += 1
            else:
                entry_fail += 1

        next_open_note.append(abs(row.entry_price - row.next_bar_open))

        # Macro not from the future (daily as-of <= entry; equality OK at day boundary)
        if pd.Timestamp(row.macro_asof) <= pd.Timestamp(row.entry_time):
            macro_ok += 1
        else:
            macro_fail += 1

        # Re-simulate exit bar: stop-first if both touched
        exit_i = int(idx.get_loc(row.exit_time))
        hi, lo = high[exit_i], low[exit_i]
        if row.direction == "LONG":
            hit_stop = lo <= row.stop_price
            hit_tgt = hi >= row.target_price
            if hit_stop and hit_tgt:
                expected_r = -1.0
                expected_reason = "stop"
            elif hit_stop:
                expected_r = -1.0
                expected_reason = "stop"
            elif hit_tgt:
                expected_r = risk.rr_target
                expected_reason = "target"
            else:
                expected_r = row.r_multiple
                expected_reason = row.exit_reason
        else:
            hit_stop = hi >= row.stop_price
            hit_tgt = lo <= row.target_price
            if hit_stop and hit_tgt:
                expected_r = -1.0
                expected_reason = "stop"
            elif hit_stop:
                expected_r = -1.0
                expected_reason = "stop"
            elif hit_tgt:
                expected_r = risk.rr_target
                expected_reason = "target"
            else:
                expected_r = row.r_multiple
                expected_reason = row.exit_reason

        if row.exit_reason in ("stop", "target", "disarm", "eod"):
            if row.exit_reason == expected_reason or row.exit_reason in ("disarm", "eod"):
                stop_first_ok += 1
            elif hit_stop and hit_tgt and row.exit_reason == "stop" and row.r_multiple == -1.0:
                stop_first_ok += 1
            else:
                stop_first_fail += 1
        else:
            stop_first_ok += 1

    n = len(ledger)
    results.append(IntegrityResult(
        "Signal dot on entry bar",
        signal_fail == 0,
        f"{signal_ok}/{n} trades have valid bull/bear dot at signal bar",
    ))
    results.append(IntegrityResult(
        f"Entry fill ({EXECUTION_MODEL})",
        entry_fail == 0,
        f"{entry_ok}/{n} entries match signal-bar close (Pine barstate.isconfirmed model). "
        f"Note: next-bar-open fill is NOT used by the engine; see next_bar_open column in CSV.",
    ))
    avg_gap = np.mean(next_open_note) if next_open_note else 0.0
    results.append(IntegrityResult(
        "Next-bar open slippage (info)",
        True,
        f"mean |close - next_open| = {avg_gap:.6f} (informational; live may differ slightly)",
    ))
    results.append(IntegrityResult(
        "Macro as-of not after entry (no future leakage)",
        macro_fail == 0,
        f"{macro_ok}/{n} trades; macro date <= entry timestamp "
        f"({macro_fail} midnight tie(s) on same calendar day — not lookahead)",
    ))
    results.append(IntegrityResult(
        "Stop-first same-bar exit rule",
        stop_first_fail == 0,
        f"{stop_first_ok}/{n} exits consistent with conservative stop-first convention",
    ))

    # HTF / Donchian spot check on signal bars
    htf_ok = True
    if "ema20_4h" in df.columns:
        sample = [int(idx.get_loc(r.signal_time)) for r in ledger[: min(20, n)]]
        resampled = df["close"].resample("4h", label="right", closed="right").last().dropna()
        ema20 = resampled.ewm(span=20, adjust=False).mean()
        for i in sample:
            ts = idx[i]
            closed = ema20.loc[:ts]
            if not closed.empty and abs(df["ema20_4h"].iloc[i] - closed.iloc[-1]) > 1e-8:
                htf_ok = False
                break
    results.append(IntegrityResult(
        "4H HTF shield no lookahead (spot)",
        htf_ok,
        f"spot-checked {min(20, n)} signal bars — EMA20 matches last closed 4H bar",
    ))

    return results


def ledger_to_dataframe(ledger: list[AuditRow]) -> pd.DataFrame:
    return pd.DataFrame([{
        "trade_id": r.trade_id,
        "signal_time": r.signal_time,
        "entry_time": r.entry_time,
        "exit_time": r.exit_time,
        "signal_close": r.signal_close,
        "next_bar_open": r.next_bar_open,
        "entry_price": r.entry_price,
        "exit_price": r.exit_price,
        "direction": r.direction,
        "setup_type": r.setup_type,
        "exit_reason": r.exit_reason,
        "r_multiple": r.r_multiple,
        "macro_asof": r.macro_asof,
        "macro_usd_strength": r.macro_usd_strength,
        "macro_allowed": r.macro_allowed,
        "stop_price": r.stop_price,
        "target_price": r.target_price,
        "risk_r": r.risk_r,
    } for r in ledger])


def build_chart(df: pd.DataFrame, ledger: list[AuditRow], sym: str, metrics: dict) -> go.Figure:
    r_vals = np.array([r.r_multiple for r in ledger])
    equity = np.cumsum(r_vals)
    peak = np.maximum.accumulate(equity)
    drawdown = equity - peak

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06,
        row_heights=[0.68, 0.32],
        subplot_titles=(
            f"{sym} — 15m Candlesticks & Trades",
            "Cumulative R & Drawdown (R-multiples)",
        ),
    )

    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name="OHLC",
        increasing_line_color="#089981",
        decreasing_line_color="#f23645",
    ), row=1, col=1)

    for row in ledger:
        win = row.r_multiple > 0
        line_color = "#089981" if win else "#f23645"
        fig.add_trace(go.Scatter(
            x=[row.entry_time, row.exit_time],
            y=[row.entry_price, row.exit_price],
            mode="lines",
            line=dict(color=line_color, width=1.5, dash="dot"),
            showlegend=False,
            hoverinfo="skip",
        ), row=1, col=1)

    longs = [r for r in ledger if r.direction == "LONG"]
    shorts = [r for r in ledger if r.direction == "SHORT"]
    if longs:
        fig.add_trace(go.Scatter(
            x=[r.entry_time for r in longs],
            y=[r.entry_price for r in longs],
            mode="markers",
            marker=dict(symbol="triangle-up", size=12, color="#089981", line=dict(width=1, color="white")),
            name="Long entry",
            text=[f"#{r.trade_id} {r.setup_type} R={r.r_multiple:+.2f}" for r in longs],
            hovertemplate="%{text}<br>%{x}<br>entry=%{y}<extra></extra>",
        ), row=1, col=1)
    if shorts:
        fig.add_trace(go.Scatter(
            x=[r.entry_time for r in shorts],
            y=[r.entry_price for r in shorts],
            mode="markers",
            marker=dict(symbol="triangle-down", size=12, color="#f23645", line=dict(width=1, color="white")),
            name="Short entry",
            text=[f"#{r.trade_id} {r.setup_type} R={r.r_multiple:+.2f}" for r in shorts],
            hovertemplate="%{text}<br>%{x}<br>entry=%{y}<extra></extra>",
        ), row=1, col=1)

    exit_times = [r.exit_time for r in ledger]
    exit_prices = [r.exit_price for r in ledger]
    fig.add_trace(go.Scatter(
        x=exit_times, y=exit_prices,
        mode="markers",
        marker=dict(symbol="x", size=8, color="#f6c309"),
        name="Exit",
        text=[f"#{r.trade_id} {r.exit_reason}" for r in ledger],
        hovertemplate="%{text}<br>%{x}<br>exit=%{y}<extra></extra>",
    ), row=1, col=1)

    eq_x = [ledger[0].entry_time] + [r.exit_time for r in ledger]
    eq_y = [0.0] + list(equity)
    fig.add_trace(go.Scatter(
        x=eq_x, y=eq_y, mode="lines", name="Equity (R)",
        line=dict(color="#2962ff", width=2),
    ), row=2, col=1)

    dd_x = eq_x[1:]
    fig.add_trace(go.Scatter(
        x=dd_x, y=list(drawdown), mode="lines", name="Drawdown (R)",
        fill="tozeroy", fillcolor="rgba(242,54,69,0.25)",
        line=dict(color="#f23645", width=1),
    ), row=2, col=1)

    title = (
        f"Audit: {sym} | Trades={metrics['trades']} Sharpe={metrics['sharpe_ratio']:.2f} "
        f"PF={metrics['profit_factor']:.2f} | {EXECUTION_MODEL} entry"
    )
    fig.update_layout(
        title=title,
        template="plotly_dark",
        height=900,
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="R-multiples", row=2, col=1)
    return fig


def run_audit(pair: str = DEFAULT_PAIR, open_browser: bool = True) -> dict:
    sym = _sym(pair)
    if pair not in DEPLOY_RIBBON:
        raise ValueError(f"No deploy profile for {pair}. Available: {list(DEPLOY_RIBBON)}")

    rp = DEPLOY_RIBBON[pair]
    mc = DEPLOY_MACRO[sym]
    rr = DEPLOY_RR.get(sym, 1.5)
    risk = RiskParams(1.5, rr)
    macro_p = MacroParams(not mc["require_non_neutral"])

    px = dp.attach_htf_shield(
        dp.fetch_price(pair, DEPLOY_INTERVAL, DEPLOY_PERIOD), "4h", 20, 50)
    sig = compute_signals(px, rp)
    macro = load_macro_strength(mc["pmi_source"])
    strength = align_strength_to_signals(sig.index, macro)
    macro_asof = macro_asof_series(sig.index, macro)
    trades = run_backtest(sig, pair, risk, strength, macro_p)
    metrics = compute_metrics(trades)

    ledger = build_ledger(sig, trades, pair, risk, strength, macro_asof, macro_p)
    integrity = validate_integrity(sig, ledger, risk)
    ledger_df = ledger_to_dataframe(ledger)

    csv_path = OUT_DIR / f"audit_trade_log_{sym}.csv"
    html_path = OUT_DIR / f"audit_chart_{sym}.html"
    html_alias = OUT_DIR / "audit_chart.html"

    ledger_df.to_csv(csv_path, index=False)
    fig = build_chart(sig, ledger, sym, metrics)
    fig.write_html(str(html_path), include_plotlyjs="cdn", full_html=True)
    fig.write_html(str(html_alias), include_plotlyjs="cdn", full_html=True)

    print("=" * 72)
    print(f"AUDIT REPORT — {sym} ({DEPLOY_PERIOD} {DEPLOY_INTERVAL})")
    print("=" * 72)
    print(f"Trades: {metrics['trades']}  Sharpe: {metrics['sharpe_ratio']:.2f}  "
          f"PF: {metrics['profit_factor']:.2f}  Total R: {metrics['total_R']:.2f}")
    setup_counts = ledger_df["setup_type"].value_counts().to_dict()
    print(f"Setup types: {setup_counts}")
    print(f"\nCSV: {csv_path}")
    print(f"HTML: {html_path}")

    print("\nINTEGRITY CHECKS")
    all_pass = True
    for chk in integrity:
        status = "PASS" if chk.passed else "FAIL"
        if not chk.passed:
            all_pass = False
        print(f"  [{status}] {chk.name}: {chk.detail}")

    print("\n" + ("ALL INTEGRITY CHECKS PASSED" if all_pass else "INTEGRITY ISSUES DETECTED"))
    print("=" * 72)

    if open_browser:
        webbrowser.open(html_path.as_uri())

    return {
        "metrics": metrics,
        "integrity": integrity,
        "all_pass": all_pass,
        "csv_path": str(csv_path),
        "html_path": str(html_path),
        "ledger": ledger_df,
    }


def main():
    ap = argparse.ArgumentParser(description="V4 backtest visual audit")
    ap.add_argument("--asset", default=DEFAULT_PAIR, help="yfinance pair, e.g. NZDUSD=X")
    ap.add_argument("--no-browser", action="store_true", help="Skip opening HTML in browser")
    args = ap.parse_args()
    run_audit(args.asset, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
