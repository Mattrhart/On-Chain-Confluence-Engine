# Asset-Specific FV Ribbon Deployments

Load **one script per chart** in TradingView. Layer 2 (6-pillar macro) runs on your Python server — these Pine files are Layer 1 only.

| File | Chart(s) | Layer 1 gate |
|------|----------|--------------|
| `strategy_main.pine` | New / test assets | Baseline (default chop + gap) |
| `strategy_eth.pine` | ETHUSD, ETHUSDT | σ-angle ≥ 6° (magnitude) |
| `strategy_aud_nzd.pine` | AUDUSD, NZDUSD | σ-angle ≥ 10° + directional |
| `strategy_jpy.pine` | USDJPY | chop_strong (gap 1.0, slope 0.06) |

**Webhook alert message** (configure in TradingView alert dialog):
```json
{"ticker":"{{ticker}}","price":{{close}},"direction":"LONG","timeframe":"{{interval}}","secret_token":"YOUR_SECRET"}
```
Use `"direction":"SHORT"` for short alerts.

All scripts use hardened non-repainting 4H shield + `barstate.isconfirmed` dots.
