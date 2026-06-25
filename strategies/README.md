# Asset-Specific FV Ribbon Deployments (Optimizer-Tuned)

Load **one script per chart** in TradingView. Layer 2 (6-pillar macro) runs on your Python server — these Pine files are Layer 1 only.

| File | Chart(s) | Optimized params | Sharpe |
|------|----------|------------------|--------|
| `strategy_eth.pine` | ETHUSD, ETHUSDT | EMA10/SMA70, σ≥12°, RR 1:3 | 1.82 |
| `strategy_aud_nzd.pine` | **AUDUSD only** | EMA30/SMA80, σ≥12° dir, RR 1:1.5 | 2.25 |
| `strategy_nzd.pine` | NZDUSD | EMA15/SMA60, σ≥7° dir, RR 1:1.5 | 1.82 |
| `strategy_jpy.pine` | USDJPY | EMA25/SMA50, chop_strong, RR 1:3 | 1.22 |
| `strategy_chf.pine` | USDCHF | EMA10/SMA50, σ≥12° dir, RR 1:1.5 | 2.13 |
| `strategy_main.pine` | New / test assets | Baseline (default chop + gap) | — |

**Webhook alert message** (replace `YOUR_SECRET`):
```json
{"ticker":"{{ticker}}","price":{{close}},"direction":"LONG","timeframe":"{{interval}}","rr_target":1.5,"atr_sl_mult":1.5,"secret_token":"YOUR_SECRET"}
```

Per-asset Layer 2 settings (PMI source, no-neutral) live in `app/trading_config.py` — updated by `backtester/optimize.py`.

All scripts use hardened non-repainting 4H shield (fixed 20/50) + `barstate.isconfirmed` dots.
