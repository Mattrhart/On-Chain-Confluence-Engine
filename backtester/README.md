# FV Ribbon Backtester

A **$0**, Forex-first backtester that ports the FV Ribbon (Layer 1) to Python and
tests whether the **"Weight of the Dollar"** macro filter (Layer 2) actually adds
edge — by running the same signals **with and without** the DXY filter and putting
the numbers side by side.

## Why this exists
- TradingView's Strategy Tester only measures **Layer 1** (price + Pine logic). It is
  blind to the macro/on-chain filter that the live engine relies on.
- This tool measures **Layer 1 vs Layer 1 + Layer 2** so the macro filter has to
  *prove* it improves results before we wire it into a live executor.

## Data (all free, no paid plan)
- **Price:** `yfinance` — Forex (`GBPUSD=X`, `AUDUSD=X`), crypto (`BTC-USD`), etc.
- **Macro:** FRED public CSV endpoint (no API key) — `DTWEXBGS` (broad USD index),
  `DGS10` / `DGS2` (Treasury yields).

## Install
```bash
cd backtester
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run
```bash
python run.py                              # GBPUSD + AUDUSD, 1h, ~2yr, L1 vs L1+DXY
python run.py --interval 1d --period 10y   # daily, deep history
python run.py --pairs GBPUSD=X EURUSD=X --rr 2.0 --atr-mult 1.5 --lookback 30
python run.py --no-neutral                 # only trade when USD regime is decisive
```

## How to read the output
A GitHub-style table with two rows per pair:

| mode | meaning |
|------|---------|
| `L1 only`  | raw FV Ribbon signals, no macro filter |
| `L1 + DXY` | same signals, kept only when they align with the USD regime |

The DXY filter **earns its place only if** it lifts `profit_factor` / `expectancy_R`
and/or cuts `max_drawdown_pct` **without** collapsing `trades` down to a handful
(small samples are noise, not edge).

## No-lookahead guarantees (important for honesty)
- The **4H shield** is aligned with `merge_asof(direction="backward")` on HTF *close*
  timestamps — each base bar only sees fully-closed 4H bars (mirrors the Pine
  `expr[1] + lookahead_on` non-repaint idiom).
- **Macro** is daily and also attached via backward `merge_asof` — a signal at time
  `t` only sees macro published on or before `t`.

## Files
| file | role |
|------|------|
| `data_providers.py` | yfinance price + 4H HTF align + FRED macro |
| `fv_ribbon.py`      | Layer 1 signal port (stateful latch + first-strike retest) |
| `macro_filter.py`   | Layer 2 "Analysis Brief" USD-bias filter |
| `backtest.py`       | trade simulator (ATR stop / RR target / disarm exit) + metrics |
| `run.py`            | harness: baseline vs DXY-filtered comparison |

## Known limitations (read before trusting numbers)
- yfinance intraday history is limited (`1h` ≈ 2yr; `1m` ≈ 7d). For deep intraday,
  swap in OANDA's free practice API later — the price layer is isolated for exactly this.
- One position at a time; stop-before-target within a bar (conservative).
- `DTWEXBGS` is a broad-dollar proxy, not the exact ICE DXY. Close enough for regime
  detection; swap the series id in `data_providers.DEFAULT_MACRO_SERIES` if desired.
