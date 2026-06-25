# Asset-Specific FV Ribbon Deployments (Optimizer-Tuned)

Load **one standalone script per chart** in TradingView. Layer 2 (6-pillar macro) runs on your Python server.

**Pine has no `#include`** — each file below is a complete copy of the FV Ribbon logic with different hardcoded constants. They do **not** import or extend `strategy_main.pine`.

| File | Chart | Optimized params | Sharpe |
|------|-------|------------------|--------|
| `strategy_eth.pine` | ETHUSD, ETHUSDT | EMA10/SMA70, σ≥12°, RR 1:3 | 1.82 |
| `strategy_aud.pine` | AUDUSD | EMA30/SMA80, σ≥12° dir, RR 1:1.5 | 2.25 |
| `strategy_nzd.pine` | NZDUSD | EMA15/SMA60, σ≥7° dir, RR 1:1.5 | 1.82 |
| `strategy_jpy.pine` | USDJPY | EMA25/SMA50, chop_strong, RR 1:3 | 1.22 |
| `strategy_chf.pine` | USDCHF | EMA10/SMA50, σ≥12° dir, RR 1:1.5 | 2.13 |
| `strategy_main.pine` | **New / untested assets only** | Default 20/50, adjustable inputs, no σ-gate | — |

**Webhook alert message** (replace `YOUR_SECRET`):
```json
{"ticker":"{{ticker}}","price":{{close}},"direction":"LONG","timeframe":"{{interval}}","rr_target":1.5,"atr_sl_mult":1.5,"secret_token":"YOUR_SECRET"}
```

Per-asset Layer 2 (PMI source, no-neutral) lives in `app/trading_config.py`.

All scripts use hardened non-repainting 4H shield (fixed 20/50) + `barstate.isconfirmed` dots.
