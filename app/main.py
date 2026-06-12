import os
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from dotenv import load_dotenv
from app.notifier import send_telegram_notification
from app.nansen import fetch_full_intelligence

load_dotenv()
app = FastAPI(title="Sovereign Confluence Engine", version="5.2.0")

# --- THE EXPANDED MACRO PEAD CACHE (The 6 Pillars) ---
MACRO_CACHE = {
    "fomc": {"status": "HAWKISH", "date": "June 17, 2026 (Rate Decision)"},
    "cpi": {"status": "HOT", "date": "May 12, 2026 (Apr Data)"},       
    "yields": {"status": "RISING", "date": "Live Treasury Feed"}, 
    "nfp": {"status": "STRONG", "date": "June 5, 2026 (May Data)"},
    "retail_sales": {"status": "STRONG", "date": "June 16, 2026"},
    "pmi": {"status": "EXPANSION", "date": "June 3, 2026"}
}

# --- NEXT MACRO EVENT COUNTDOWN TARGET ---
# Target: June 17, 2026 at 18:00 UTC (FOMC Rate Decision)
NEXT_MACRO_TARGET = datetime(2026, 6, 17, 18, 0, tzinfo=timezone.utc)

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

class TradingViewPayload(BaseModel):
    ticker: str
    price: float
    direction: str
    timeframe: str
    secret_token: str

@app.get("/")
async def root():
    return {"status": "Engine V5.2.0 Active - Omnipotent USD Sentiment Routing Engaged"}

# --- OMNIPOTENT USD MACRO CALCULATOR ---
def calculate_usd_macro_bias():
    """Calculates the Net USD Strength based on the 6 Core Pillars."""
    usd_strength = 0
    reasons = []

    # 1. FOMC (The Heavyweight: +/- 3 points)
    if MACRO_CACHE["fomc"]["status"] == "HAWKISH":
        usd_strength += 3
        reasons.append(f"• <b>FOMC Tone:</b> Hawkish (+3) | <i>Higher rates -> Capital Inflows</i>")
    elif MACRO_CACHE["fomc"]["status"] == "DOVISH": 
        usd_strength -= 3
        reasons.append(f"• <b>FOMC Tone:</b> Dovish (-3) | <i>Rate cuts -> Capital Outflows</i>")

    # 2. CPI (Inflation: +/- 2 points)
    if MACRO_CACHE["cpi"]["status"] == "HOT": 
        usd_strength += 2
        reasons.append(f"• <b>Inflation:</b> CPI Hot (+2) | <i>Forces Hawkish Fed</i>")
    elif MACRO_CACHE["cpi"]["status"] == "COLD": 
        usd_strength -= 2

    # 3. Treasury Yields (+/- 2 points)
    if MACRO_CACHE["yields"]["status"] == "RISING":
        usd_strength += 2
        reasons.append(f"• <b>Yields:</b> 10Y Rising (+2) | <i>Increases USD Yield Demand</i>")
    elif MACRO_CACHE["yields"]["status"] == "FALLING": 
        usd_strength -= 2
        
    # 4. NFP (Labor: +/- 2 points)
    if MACRO_CACHE["nfp"]["status"] == "STRONG":
        usd_strength += 2
        reasons.append(f"• <b>Labor:</b> NFP Strong (+2) | <i>Delays Rate Cuts</i>")
    elif MACRO_CACHE["nfp"]["status"] == "WEAK": 
        usd_strength -= 2

    # 5. ISM PMI (Services: +/- 2 points)
    if MACRO_CACHE["pmi"]["status"] == "EXPANSION":
        usd_strength += 2
        reasons.append(f"• <b>ISM PMI:</b> Expansion >50 (+2) | <i>Service Sector Growth</i>")
    elif MACRO_CACHE["pmi"]["status"] == "CONTRACTION": 
        usd_strength -= 2

    # 6. Retail Sales (Consumer: +/- 1 point)
    if MACRO_CACHE["retail_sales"]["status"] == "STRONG":
        usd_strength += 1
        reasons.append(f"• <b>Retail Sales:</b> Strong (+1) | <i>Resilient Consumer</i>")
    elif MACRO_CACHE["retail_sales"]["status"] == "WEAK": 
        usd_strength -= 1

    return usd_strength, reasons

# --- THE BACKGROUND WORKER (Heavy Lifting) ---
async def process_tradingview_signal(payload: TradingViewPayload):
    raw_ticker = payload.ticker.upper().replace("/", "").replace("-", "").replace(" ", "").replace(".P", "")
    is_forex = len(raw_ticker) == 6 and raw_ticker[:3] in CURRENCY_KEYWORDS and raw_ticker[3:] in CURRENCY_KEYWORDS
    
    raw_dir = payload.direction.upper()
    direction = "LONG" if raw_dir in ["BUY", "LONG"] else "SHORT"
    dir_label = direction
    decision, stars, reasoning, metric_display = "EXECUTE", "⭐⭐⭐", "", "Processing Matrix..."

    # Extract Live USD Telemetry for both branches
    usd_strength, macro_reasons = calculate_usd_macro_bias()

    if is_forex:
        base_ccy, quote_ccy = raw_ticker[:3], raw_ticker[3:]
        symbol = f"{base_ccy}_{quote_ccy}"
        sector = f"Global FX | {base_ccy}-{quote_ccy} Cross"
        
        reasons = macro_reasons.copy()
        macro_bias_for_pair = 0
        
        if quote_ccy == "USD":
            macro_bias_for_pair = -usd_strength
            reasons.append(f"\n• <b>Topology:</b> USD is Quote. Pair trend inverted (Bias: {macro_bias_for_pair}).")
        elif base_ccy == "USD":
            macro_bias_for_pair = usd_strength
            reasons.append(f"\n• <b>Topology:</b> USD is Base. Pair trend direct (Bias: {macro_bias_for_pair}).")
        else:
            reasons.append("\n• <b>Topology:</b> Non-USD Cross. Evaluating on pure technicals.")

        if direction == "LONG" and macro_bias_for_pair > 0:
            decision, stars = "EXECUTE", "⭐⭐⭐⭐⭐"
            reasons.append("\n✅ <b>Decision:</b> PROCEED. Macro framework aligned with LONG setup.")
        elif direction == "SHORT" and macro_bias_for_pair < 0:
            decision, stars = "EXECUTE", "⭐⭐⭐⭐⭐"
            reasons.append("\n✅ <b>Decision:</b> PROCEED. Macro framework aligned with SHORT setup.")
        elif macro_bias_for_pair == 0:
             decision, stars = "EXECUTE", "⭐⭐⭐"
             reasons.append("\n✅ <b>Decision:</b> PROCEED. Macro environment flat. Authorized on technicals.")
        else:
            decision, stars = "ABORT", "⚠️"
            reasons.append("\n🛑 <b>Decision:</b> ABORT. Technical direction fights established macro trend.")

        metric_display = f"USD PEAD: {usd_strength}"
        reasoning = "\n".join(reasons)

    else:
        # --- CRYPTO MATRIX (NANSEN + USD MACRO) ---
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
        
        # 1. Institutional Stream (Nansen)
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

        # 2. USD Macro Overlay (Inverse Crypto Correlation)
        reasons.append("\n🌍 <b>MACRO OVERLAY (USD INVERSE CORRELATION):</b>")
        reasons.extend(macro_reasons)
        
        # Strong USD = Crypto Bearish (Short). Weak USD = Crypto Bullish (Long).
        crypto_macro_bias = -usd_strength 
        
        if direction == "LONG" and crypto_macro_bias > 0:
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
        reasoning = "\n".join(reasons)

    price_display = f"{payload.price:,.5f}" if is_forex else f"{payload.price:,.2f}"
    
    # --- TIME & COUNTDOWN LOGIC ---
    now = datetime.now(timezone.utc)
    sync_time_str = now.strftime("%Y-%m-%d %H:%M:%S UTC")
    
    if now < NEXT_MACRO_TARGET:
        delta = NEXT_MACRO_TARGET - now
        hours_left = delta.seconds // 3600
        countdown = f"{delta.days}d {hours_left}h"
    else:
        countdown = "DATA REFRESH REQUIRED"
    
    rich_message = (
        f"{'🟩' if decision == 'EXECUTE' else '🟥'} <b>DECISION: {decision} ({dir_label})</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💎 <b>Asset:</b> <code>${symbol}</code>\n"
        f"🏷️ <b>Sector:</b> <code>{sector}</code>\n"
        f"📊 <b>TF:</b> <code>{payload.timeframe}m</code> | <b>Price:</b> <code>${price_display}</code>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"{'🌍 <b>MACRO TELEMETRY</b>' if is_forex else '🛡️ <b>HYBRID INTELLIGENCE</b>'}\n"
        f"• Status: <code>{metric_display}</code>\n• Conviction: {stars}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📝 <b>Analyst Brief:</b>\n{reasoning}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⏱️ <b>Data Synced:</b> <code>{sync_time_str}</code>\n"
        f"⏳ <b>Next Macro Update:</b> <code>{countdown}</code>\n"
        f"📈 <i>Confluence Engine V5.2.0</i>"
    )

    await send_telegram_notification(rich_message)


# --- THE LIGHTNING-FAST WEBHOOK ENDPOINT ---
@app.post("/webhook/tradingview")
@app.post("/webhook/tradingview/")
async def tradingview_webhook(payload: TradingViewPayload, background_tasks: BackgroundTasks):
    if payload.secret_token != os.getenv("TRADINGVIEW_SECRET", "hype_retest_2026"): 
        raise HTTPException(status_code=401)

    background_tasks.add_task(process_tradingview_signal, payload)
    return {"status": "success", "message": "Signal securely received"}