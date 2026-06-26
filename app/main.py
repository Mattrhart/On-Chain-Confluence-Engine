import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Repo root on PYTHONPATH so `backtester.macro_pillars` resolves in production
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from dotenv import load_dotenv
from app.notifier import send_telegram_notification
from app.nansen import fetch_full_intelligence
from app.macro_live import ensure_macro_fresh, warm_macro_cache, calculate_usd_macro_bias, cache_status, live_pillar_summary
from app.trading_config import macro_settings_for_ticker, risk_settings_for_ticker, compute_atr_levels

load_dotenv()
app = FastAPI(title="Sovereign Confluence Engine", version="5.5.2")

# --- THE EQUITIES PEAD CACHE (The Heavyweights) ---
TECH_EARNINGS_CACHE = {
    "NVDA": {"surprise": "MASSIVE BEAT", "guidance": "RAISED", "weight": 3},
    "MSFT": {"surprise": "BEAT", "guidance": "STABLE", "weight": 2},
    "AAPL": {"surprise": "INLINE", "guidance": "STABLE", "weight": 0},
    "META": {"surprise": "BEAT", "guidance": "RAISED", "weight": 2},
    "AMZN": {"surprise": "BEAT", "guidance": "STABLE", "weight": 1}
}

# --- NEXT MACRO EVENT COUNTDOWN TARGET ---
NEXT_MACRO_TARGET = datetime(2026, 7, 14, 12, 30, tzinfo=timezone.utc)

# --- THE AUTO-ROUTING CORRELATION MATRIX ---
CRYPTO_CLEAN_MAP = {
    "BTC": "WBTC", "BTCUSD": "WBTC", "BTCUSDT": "WBTC",
    "ETH": "ETH",  "ETHUSD": "ETH",  "ETHUSDT": "ETH",
    "SOL": "SOL",  "SOLUSD": "SOL",  "SOLUSDT": "SOL",
    "BNB": "BNB",  "HYPE": "HYPE",   "LINK": "LINK",
    "PEPE": "PEPE", "AERO": "AERO",   "LDO": "LDO"
}

TOKEN_MAP = {
    "ETH":  {"chain": "ethereum", "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "sector": "L1 / Blue-Chip"},
    "BNB":  {"chain": "bnb",      "address": "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c", "sector": "L1 / Exchange"},
    "SOL":  {"chain": "ethereum", "address": "0xd31a59c85ae9d8edefec411d448f90841571b89c", "sector": "L1 / Speed"},
    "HYPE": {"chain": "hyperevm", "address": "0x0d01dc56dcaaca66ad901c959b4011ec", "sector": "L1 / Perp DEX"},
    "WBTC": {"chain": "ethereum", "address": "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", "sector": "Market Anchor"},
    "LINK": {"chain": "ethereum", "address": "0x514910771af9ca656af840dff83e8264ecf986ca", "sector": "Oracle / Infra"},
    "PEPE": {"chain": "ethereum", "address": "0x6982508145454ce325ddbe47a25d4ec3d2311933", "sector": "Meme / Beta"},
    "AERO": {"chain": "base",     "address": "0x94018130d41403512255c276587be09d43526f8d", "sector": "L2 / DEX"},
    "LDO":  {"chain": "ethereum", "address": "0x5a98781ae4372f810be444d32c815bc0c612b5e1", "sector": "LSD / Staking"}
}

CURRENCY_KEYWORDS = {
    "USD": [], "EUR": [], "GBP": [], "CHF": [],
    "JPY": [], "AUD": [], "CAD": [], "NZD": []
}

INDEX_KEYWORDS = ["NDX", "NAS", "SPX", "US30", "DJI", "MNQ"]


class TradingViewPayload(BaseModel):
    ticker: str
    price: float
    direction: str
    timeframe: str
    secret_token: str
    # Optional — Pine sends these for ATR stop routing (V5.5.2+)
    risk_atr: float | None = None
    atr_sl_mult: float | None = None
    rr_target: float | None = None
    signal_time: int | None = None  # bar open time ms (TradingView {{time}})


@app.on_event("startup")
async def _startup_macro_cache():
    """Warm the 6-pillar FRED cache before the first webhook."""
    await warm_macro_cache()


@app.get("/")
async def root():
    status = cache_status()
    return {
        "status": "Engine V5.5.1 Active - Live 6-Pillar Macro Engaged",
        "macro_cache": status,
    }


# --- TECH PEAD CALCULATOR ---
def calculate_tech_pead_bias():
    """Calculates the Net Earnings Drift for Tech Indices."""
    pead_score = 0
    reasons = []

    for ticker, data in TECH_EARNINGS_CACHE.items():
        pead_score += data["weight"]

        if data["weight"] > 0:
            reasons.append(f"• <b>{ticker} Earnings:</b> {data['surprise']} (+{data['weight']}) | <i>Guidance: {data['guidance']}</i>")
        elif data["weight"] < 0:
            reasons.append(f"• <b>{ticker} Earnings:</b> {data['surprise']} ({data['weight']}) | <i>Guidance: {data['guidance']}</i>")

    state_summary = ""
    if pead_score >= 5:
        state_summary = "\n🚀 <b>INDEX STATE: Institutional Accumulation</b>\n<i>Heavyweight earnings crush. NDX is in a structured, multi-week upward drift. Shorts are incredibly dangerous.</i>"
    elif pead_score <= -5:
        state_summary = "\n🩸 <b>INDEX STATE: Capital Flight</b>\n<i>Heavyweights missed. NDX is under heavy distribution. Longs are dangerous.</i>"
    else:
        state_summary = "\n⚖️ <b>INDEX STATE: Mixed/Neutral</b>\n<i>Earnings season mixed. Index will track broader USD Macro and technicals over pure PEAD.</i>"

    reasons.append(state_summary)
    return pead_score, reasons


def _nansen_enabled() -> bool:
    """Skip Nansen when no API key or SKIP_NANSEN=true (macro-only crypto gate)."""
    if os.getenv("SKIP_NANSEN", "").lower() in ("1", "true", "yes"):
        return False
    return bool(os.getenv("NANSEN_API_KEY"))


def _macro_decision(direction: str, macro_bias: int, require_non_neutral: bool) -> tuple[str, str, str]:
    """Return (decision, stars, reason_line) from directional macro bias."""
    if require_non_neutral and macro_bias == 0:
        return "ABORT", "⚠️", "\n🛑 <b>Decision:</b> ABORT. No-neutral policy — macro bias is flat (0)."
    if direction == "LONG" and macro_bias > 0:
        return "EXECUTE", "⭐⭐⭐⭐⭐", "\n✅ <b>Decision:</b> PROCEED. Macro framework aligned with LONG setup."
    if direction == "SHORT" and macro_bias < 0:
        return "EXECUTE", "⭐⭐⭐⭐⭐", "\n✅ <b>Decision:</b> PROCEED. Macro framework aligned with SHORT setup."
    if macro_bias == 0:
        return "EXECUTE", "⭐⭐⭐", "\n✅ <b>Decision:</b> PROCEED. Macro environment flat. Authorized on technicals."
    return "ABORT", "⚠️", "\n🛑 <b>Decision:</b> ABORT. Technical direction fights established macro trend."


# --- THE BACKGROUND WORKER (Heavy Lifting) ---
async def process_tradingview_signal(payload: TradingViewPayload):
    await ensure_macro_fresh()

    raw_ticker = payload.ticker.upper().replace("/", "").replace("-", "").replace(" ", "").replace(".P", "")
    is_forex = len(raw_ticker) == 6 and raw_ticker[:3] in CURRENCY_KEYWORDS and raw_ticker[3:] in CURRENCY_KEYWORDS
    is_index = any(keyword in raw_ticker for keyword in INDEX_KEYWORDS)

    raw_dir = payload.direction.upper()
    direction = "LONG" if raw_dir in ["BUY", "LONG"] else "SHORT"
    dir_label = direction
    decision, stars, reasoning, metric_display = "EXECUTE", "⭐⭐⭐", "", "Processing Matrix..."

    macro_cfg = macro_settings_for_ticker(raw_ticker)
    usd_strength, macro_reasons = calculate_usd_macro_bias(pmi_source=macro_cfg["pmi_source"])

    narrative_points = [p for p in macro_reasons if not p.startswith("\n")]
    state_summary_block = [p for p in macro_reasons if p.startswith("\n")]
    state_summary = state_summary_block[0] if state_summary_block else ""

    if is_index:
        symbol = raw_ticker
        sector = "Global Indices | Tech Heavy"

        pead_score, pead_reasons = calculate_tech_pead_bias()
        reasons = [p for p in pead_reasons if not p.startswith("\n")]
        index_state_summary = [p for p in pead_reasons if p.startswith("\n")][0]

        reasons.append("\n🌍 <b>MACRO OVERLAY (Yield Pressure):</b>")
        reasons.extend(narrative_points)

        index_bias = pead_score - (usd_strength * 0.5)

        if direction == "LONG" and index_bias > 0:
            decision, stars = "EXECUTE", "⭐⭐⭐⭐⭐"
            reasons.append(f"\n✅ <b>Decision:</b> PROCEED. Earnings PEAD supports LONG drift.")
        elif direction == "SHORT" and index_bias < 0:
            decision, stars = "EXECUTE", "⭐⭐⭐⭐⭐"
            reasons.append(f"\n✅ <b>Decision:</b> PROCEED. Earnings PEAD supports SHORT drift.")
        elif index_bias == 0:
            decision, stars = "EXECUTE", "⭐⭐⭐"
            reasons.append("\n✅ <b>Decision:</b> PROCEED. PEAD is flat. Authorized on technicals.")
        else:
            decision, stars = "ABORT", "⚠️"
            reasons.append("\n🛑 <b>Decision:</b> ABORT. Technical direction fights established Earnings PEAD.")

        reasons.append(index_state_summary)
        metric_display = f"PEAD Score: {pead_score} | Macro Drag: {-(usd_strength * 0.5)}"
        reasoning = "\n".join(reasons)

    elif is_forex:
        base_ccy, quote_ccy = raw_ticker[:3], raw_ticker[3:]
        symbol = f"{base_ccy}_{quote_ccy}"
        sector = f"Global FX | {base_ccy}-{quote_ccy} Cross"

        reasons = narrative_points.copy()
        macro_bias_for_pair = 0

        if quote_ccy == "USD":
            macro_bias_for_pair = -usd_strength
            reasons.append(f"\n• <b>Topology:</b> USD is Quote. Pair trend inverted (Bias: {macro_bias_for_pair}).")
        elif base_ccy == "USD":
            macro_bias_for_pair = usd_strength
            reasons.append(f"\n• <b>Topology:</b> USD is Base. Pair trend direct (Bias: {macro_bias_for_pair}).")
        else:
            reasons.append("\n• <b>Topology:</b> Non-USD Cross. Evaluating on pure technicals.")

        reasons.append(f"\n• <b>Live FRED:</b> <code>{live_pillar_summary(macro_cfg['pmi_source'])}</code>")

        decision, stars, line = _macro_decision(
            direction, macro_bias_for_pair, macro_cfg["require_non_neutral"])
        reasons.append(line)

        if state_summary:
            reasons.append(state_summary)

        metric_display = f"USD PEAD: {usd_strength} | PMI: {macro_cfg['pmi_source']}"
        reasoning = "\n".join(reasons)

    else:
        lookup_key = raw_ticker.split(":")[-1]
        for stable in ["USDT", "USDC", "USD"]:
            if lookup_key.endswith(stable) and lookup_key != stable:
                lookup_key = lookup_key[:-len(stable)]
                break

        symbol = CRYPTO_CLEAN_MAP.get(lookup_key, lookup_key)
        token_info = TOKEN_MAP.get(symbol)

        if not token_info:
            print(f"🛑 GHOST LAYER: {symbol} bypassed. Tracking matrix clean.")
            return

        sector = token_info.get("sector")
        crypto_macro_bias = -usd_strength

        if not _nansen_enabled():
            # Macro-only crypto gate (ETH without Nansen subscription)
            reasons = ["🛡️ <b>INSTITUTIONAL LAYER:</b>",
                       "• <b>Nansen:</b> Bypassed — macro-only mode (set NANSEN_API_KEY to re-enable)."]
            reasons.append("\n🌍 <b>MACRO OVERLAY (USD INVERSE CORRELATION):</b>")
            reasons.extend(narrative_points)
            reasons.append(f"\n• <b>Live FRED:</b> <code>{live_pillar_summary(macro_cfg['pmi_source'])}</code>")
            decision, stars, line = _macro_decision(
                direction, crypto_macro_bias, macro_cfg["require_non_neutral"])
            reasons.append(line)
            if state_summary:
                reasons.append(state_summary)
            metric_display = f"USD Score: {usd_strength} | PMI: {macro_cfg['pmi_source']} | Macro-Only"
            reasoning = "\n".join(reasons)
        else:
            metrics = await fetch_full_intelligence(symbol=symbol, address=token_info.get("address"), chain=token_info.get("chain"))
            if not metrics:
                metrics = {"net_flow_24h": 0, "cex_netflow": 0, "perp_bias": "NEUTRAL"}

            smart_money_flow = metrics.get("net_flow_24h", 0)
            metric_display = f"${smart_money_flow/1e6:+.2f}M Flow | USD Score: {usd_strength}" if abs(smart_money_flow) >= 1_000_000 else f"${smart_money_flow/1e3:+.1f}K Flow | USD Score: {usd_strength}"

            confluence_score = 0
            reasons = []
            reasons.append("🛡️ <b>INSTITUTIONAL LAYER:</b>")

            if direction == "LONG" and smart_money_flow > 500_000:
                confluence_score += 3
                reasons.append("• <b>Nansen:</b> Smart Money Accumulation Mapped (+3)")
            elif direction == "SHORT" and smart_money_flow < -500_000:
                confluence_score += 3
                reasons.append("• <b>Nansen:</b> Smart Money Heavy Distribution Mapped (+3)")
            else:
                reasons.append("• <b>Nansen:</b> Smart Money Null [Restrict].")

            reasons.append("\n🌍 <b>MACRO OVERLAY (USD INVERSE CORRELATION):</b>")
            reasons.extend(narrative_points)
            reasons.append(f"\n• <b>Live FRED:</b> <code>{live_pillar_summary(macro_cfg['pmi_source'])}</code>")

            if macro_cfg["require_non_neutral"] and crypto_macro_bias == 0:
                confluence_score -= 3
                reasons.append("\n• <b>Macro Alignment:</b> ⚠️ No-neutral policy — flat USD macro (-3)")
            elif direction == "LONG" and crypto_macro_bias > 0:
                confluence_score += 3
                reasons.append(f"\n• <b>Macro Alignment:</b> USD Weakness Supports Crypto LONG (+3)")
            elif direction == "SHORT" and crypto_macro_bias < 0:
                confluence_score += 3
                reasons.append(f"\n• <b>Macro Alignment:</b> USD Strength Supports Crypto SHORT (+3)")
            elif crypto_macro_bias == 0:
                reasons.append(f"\n• <b>Macro Alignment:</b> Neutral USD Environment (+0)")
            else:
                confluence_score -= 3
                reasons.append(f"\n• <b>Macro Alignment:</b> ⚠️ Technical direction fights USD Macro framework (-3)")

            if confluence_score >= 3:
                decision, stars = "EXECUTE", "⭐⭐⭐⭐⭐"
                reasons.append(f"\n✅ <b>Decision:</b> PROCEED. Confluence threshold met.")
            else:
                decision, stars = "ABORT", "⚠️"
                reasons.append(f"\n🛑 <b>Decision:</b> ABORT. Insufficient confluence threshold to support technicals.")

            reasons.append(f"📊 <b>Confluence Score: {confluence_score}/6</b>")

            if state_summary:
                reasons.append(state_summary)

            reasoning = "\n".join(reasons)

    price_display = f"{payload.price:,.5f}" if is_forex else f"{payload.price:,.2f}"

    now = datetime.now(timezone.utc)
    sync_time_str = now.strftime("%Y-%m-%d %H:%M:%S UTC")
    cache = cache_status()
    macro_sync = cache.get("fetched_at") or sync_time_str

    if now < NEXT_MACRO_TARGET:
        delta = NEXT_MACRO_TARGET - now
        hours_left = delta.seconds // 3600
        countdown = f"{delta.days}d {hours_left}h"
    else:
        countdown = "DATA REFRESH REQUIRED"

    # --- Signal lock + stop levels (V5.5.2) ---
    risk_cfg = risk_settings_for_ticker(raw_ticker)
    stop_block = ""
    if payload.signal_time:
        bar_ts = datetime.fromtimestamp(payload.signal_time / 1000, tz=timezone.utc)
        stop_block += f"\n🔒 <b>Signal locked:</b> <code>{bar_ts.strftime('%Y-%m-%d %H:%M UTC')}</code> bar close\n"
        stop_block += "<i>Later ribbon/disarm changes do NOT revoke this alert.</i>\n"

    if risk_cfg["stop_mode"] == "atr" and payload.risk_atr and payload.risk_atr > 0:
        mult = payload.atr_sl_mult or risk_cfg["atr_sl_mult"]
        rr = payload.rr_target or risk_cfg["rr_target"]
        lv = compute_atr_levels(direction, payload.price, payload.risk_atr, mult, rr)
        stop_block += (
            f"\n🎯 <b>ATR Stop Model</b> (auto)\n"
            f"• Stop: <code>{lv['stop']:,.5f}</code>\n"
            f"• Target ({rr}R): <code>{lv['target']:,.5f}</code>\n"
            f"• Risk: <code>{lv['risk_points']:,.5f}</code> ({mult}× ATR)\n"
        )
    elif risk_cfg["stop_mode"] == "manual":
        stop_block += (
            "\n📐 <b>Stop:</b> <code>MANUAL</code> — place below/above 15m structure "
            "or OB wick (your discretion)\n"
        )

    rich_message = (
        f"{'🟩' if decision == 'EXECUTE' else '🟥'} <b>DECISION: {decision} ({dir_label})</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💎 <b>Asset:</b> <code>${symbol}</code>\n"
        f"🏷️ <b>Sector:</b> <code>{sector}</code>\n"
        f"📊 <b>TF:</b> <code>{payload.timeframe}m</code> | <b>Price:</b> <code>${price_display}</code>\n"
        f"{stop_block}"
        f"━━━━━━━━━━━━━━━\n"
        f"{'🌍 <b>MACRO TELEMETRY</b>' if is_forex or is_index else '🛡️ <b>HYBRID INTELLIGENCE</b>'}\n"
        f"• Status: <code>{metric_display}</code>\n• Conviction: {stars}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📝 <b>Analyst Brief:</b>\n{reasoning}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⏱️ <b>Data Synced:</b> <code>{sync_time_str}</code>\n"
        f"🔄 <b>Macro Cache:</b> <code>{macro_sync}</code>\n"
        f"⏳ <b>Next Macro Event:</b> <code>{countdown}</code>\n"
        f"📈 <i>Confluence Engine V5.5.2</i>"
    )

    await send_telegram_notification(rich_message)


@app.get("/test-alert")
async def test_alert(ticker: str = "AUDUSD", direction: str = "LONG"):
    """
    Send a live Telegram test using current FRED macro cache.
    Optional query: ?ticker=ETHUSD&direction=SHORT
    """
    secret = os.getenv("TRADINGVIEW_SECRET", "hype_retest_2026")
    payload = TradingViewPayload(
        ticker=ticker,
        price=1.0 if "USD" in ticker.upper() and "ETH" not in ticker.upper() else 3500.0,
        direction=direction,
        timeframe="15",
        secret_token=secret,
        risk_atr=0.0012 if "USD" in ticker.upper() else 45.0,
        signal_time=int(datetime.now(timezone.utc).timestamp() * 1000),
    )
    await process_tradingview_signal(payload)
    return {
        "status": "sent",
        "ticker": ticker,
        "direction": direction,
        "fred_oecd": live_pillar_summary("oecd"),
        "fred_ism": live_pillar_summary("ism"),
        "macro_cache": cache_status(),
    }


@app.post("/webhook/tradingview")
@app.post("/webhook/tradingview/")
async def tradingview_webhook(payload: TradingViewPayload, background_tasks: BackgroundTasks):
    if payload.secret_token != os.getenv("TRADINGVIEW_SECRET", "hype_retest_2026"):
        raise HTTPException(status_code=401)

    background_tasks.add_task(process_tradingview_signal, payload)
    return {"status": "success", "message": "Signal securely received"}
