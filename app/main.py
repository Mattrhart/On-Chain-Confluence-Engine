import os
import re
import httpx
import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from dotenv import load_dotenv
from app.notifier import send_telegram_notification
from app.nansen import fetch_full_intelligence

load_dotenv()
app = FastAPI(title="Sovereign Confluence Engine", version="5.0")

# --- THE MACRO PEAD CACHE ---
# Updated to track release dates and duration of the macro trend
MACRO_CACHE = {
    "cpi": {"status": "HOT", "date": "May 12, 2026 (Apr Data)"},       
    "yields": {"status": "RISING", "date": "Live Treasury Feed"}, 
    "nfp": {"status": "STRONG", "date": "June 5, 2026 (May Data)"}     
}

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
    return {"status": "Engine V5.0 Active"}

async def fetch_dex_liquidity_usd(chain: str, address: str) -> float:
    if chain.lower() == "solana": return 5000000.0
    if chain.lower() == "hyperevm": return 3500000.0
    url = f"https://api.geckoterminal.com/api/v2/networks/{chain.lower()}/tokens/{address}/pools?page=1"
    headers = {"Accept": "application/json;version=20230302"}
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json().get("data", [])
                return sum([float(pool.get("attributes", {}).get("reserve_in_usd", 0.0)) for pool in data])
        except: pass
    return 1000000.0

@app.post("/webhook/tradingview")
@app.post("/webhook/tradingview/")
async def tradingview_webhook(payload: TradingViewPayload, background_tasks: BackgroundTasks):
    if payload.secret_token != os.getenv("TRADINGVIEW_SECRET", "hype_retest_2026"): raise HTTPException(status_code=401)

    raw_ticker = payload.ticker.upper().replace("/", "").replace("-", "").replace(" ", "").replace(".P", "")
    is_forex = len(raw_ticker) == 6 and raw_ticker[:3] in CURRENCY_KEYWORDS and raw_ticker[3:] in CURRENCY_KEYWORDS
    
    raw_dir = payload.direction.upper()
    direction = "LONG" if raw_dir in ["BUY", "LONG"] else "SHORT"
    dir_label = direction
    decision, stars, reasoning, metric_display = "EXECUTE", "⭐⭐⭐", "", "Processing Data Matrix..."

    if is_forex:
        base_ccy, quote_ccy = raw_ticker[:3], raw_ticker[3:]
        symbol = f"{base_ccy}_{quote_ccy}"
        sector = f"Global FX | {base_ccy}-{quote_ccy} Cross"
        
        # 🛡️ THE FOREX MACRO PEAD MATRIX
        usd_strength = 0
        reasons = []

        # 1. Calculate USD Strength from Cache & Explain Economic Impact
        if MACRO_CACHE["cpi"]["status"] == "HOT": 
            usd_strength += 2
            reasons.append(f"• <b>Inflation:</b> CPI Hot (+2) | <i>Increases USD Value (Hawkish Fed)</i> | Updated: {MACRO_CACHE['cpi']['date']}")
        elif MACRO_CACHE["cpi"]["status"] == "COLD":
            usd_strength -= 2
            
        if MACRO_CACHE["yields"]["status"] == "RISING":
            usd_strength += 2
            reasons.append(f"• <b>Yields:</b> 10Y Treasury Rising (+2) | <i>Increases USD Value (Capital Inflows)</i> | Updated: {MACRO_CACHE['yields']['date']}")
        elif MACRO_CACHE["yields"]["status"] == "FALLING":
            usd_strength -= 2
            
        if MACRO_CACHE["nfp"]["status"] == "STRONG":
            usd_strength += 2
            reasons.append(f"• <b>Labor:</b> NFP Strong (+2) | <i>Increases USD Value (Rate Cut Delay)</i> | Updated: {MACRO_CACHE['nfp']['date']}")
        elif MACRO_CACHE["nfp"]["status"] == "WEAK":
            usd_strength -= 2

        # 2. The Dynamic Flipper (Explicit Inversion Logic)
        macro_bias_for_pair = 0
        if quote_ccy == "USD":
            # e.g., EUR/USD. Strong USD pushes pair down.
            macro_bias_for_pair = -usd_strength
            reasons.append(f"\n• <b>Topology:</b> USD is Quote ({base_ccy}/{quote_ccy}). A stronger Dollar inherently suppresses the base currency, driving the pair's price DOWN. Pair trend inverted (Bias: {macro_bias_for_pair}).")
        elif base_ccy == "USD":
            # e.g., USD/JPY. Strong USD pushes pair up.
            macro_bias_for_pair = usd_strength
            reasons.append(f"\n• <b>Topology:</b> USD is Base ({base_ccy}/{quote_ccy}). A stronger Dollar directly drives the pair's price UP. Pair trend direct (Bias: {macro_bias_for_pair}).")
        else:
            reasons.append("\n• <b>Topology:</b> Non-USD Cross. Evaluating on pure technicals.")

        # 3. Execution Alignment
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
        # --- CRYPTO GHOST LAYER & MATRIX ---
        lookup_key = raw_ticker.split(":")[-1]
        for stable in ["USDT", "USDC", "USD"]:
            if lookup_key.endswith(stable) and lookup_key != stable:
                lookup_key = lookup_key[:-len(stable)]
                break
        
        symbol = CRYPTO_CLEAN_MAP.get(lookup_key, lookup_key)
        token_info = TOKEN_MAP.get(symbol)

        if not token_info:
            print(f"🛑 GHOST LAYER: {symbol} bypassed. Tracking matrix clean.")
            return {"status": "ignored", "reason": "Asset not configured."}

        sector = token_info.get("sector")
        pool_liquidity = await fetch_dex_liquidity_usd(chain=token_info.get("chain"), address=token_info.get("address"))
        
        metrics = await fetch_full_intelligence(symbol=symbol, address=token_info.get("address"), chain=token_info.get("chain"))
        if not metrics:
            metrics = {"net_flow_24h": 0, "cex_netflow": 0, "perp_bias": "NEUTRAL"}

        smart_money_flow = metrics.get("net_flow_24h", 0)
        cex_24h_netflow = metrics.get("cex_netflow", 0)
        perp_leaderboard_bias = metrics.get("perp_bias", "NEUTRAL")

        if abs(smart_money_flow) >= 1_000_000: metric_display = f"${smart_money_flow/1e6:+.2f}M Flow"
        else: metric_display = f"${smart_money_flow/1e3:+.1f}K Flow"

        confluence_score = 0
        reasons = []

        if direction == "LONG" and smart_money_flow > 500_000:
            confluence_score += 3
            reasons.append("• <b>Primary Stream:</b> Smart Money Accumulation Mapped (+3)")
        elif direction == "SHORT" and smart_money_flow < -500_000:
            confluence_score += 3
            reasons.append("• <b>Primary Stream:</b> Smart Money Heavy Distribution Mapped (+3)")
        else:
            reasons.append("• <b>Primary Stream:</b> Smart Money Flow Flat/Neutral (+0) [Free Tier Limit]")

        if direction == "LONG" and cex_24h_netflow < -100_000:
            confluence_score += 2
            reasons.append("• <b>Secondary Stream:</b> Exchange Supply Shock / Outflows Verified (+2)")
        elif direction == "SHORT" and cex_24h_netflow > 100_000:
            confluence_score += 2
            reasons.append("• <b>Secondary Stream:</b> Exchange Inflows / Increase in Sell Pressures (+2)")
        else:
            reasons.append("• <b>Secondary Stream:</b> Exchange Supply Balance Stable (+0)")

        if direction == "LONG" and perp_leaderboard_bias == "LONG":
            confluence_score += 2
            reasons.append("• <b>Tertiary Stream:</b> High-PnL Perp Traders Positioned LONG (+2)")
        elif direction == "SHORT" and perp_leaderboard_bias == "SHORT":
            confluence_score += 2
            reasons.append("• <b>Tertiary Stream:</b> High-PnL Perp Traders Positioned SHORT (+2)")
        else:
            reasons.append("• <b>Tertiary Stream:</b> Derivatives Bias Neutral (+0)")

        if pool_liquidity < 250000.0:
            decision, stars = "ABORT", "⚠️"
            reasons.append(f"\n🛑 <b>CRITICAL RISK:</b> Liquidity depth sub-optimal (${pool_liquidity/1e3:,.0f}k).")
        else:
            if confluence_score >= 3:
                decision, stars = "EXECUTE", "⭐⭐⭐⭐⭐"
                reasons.append(f"\n✅ <b>Decision:</b> PROCEED. Confluence threshold met.")
            else:
                decision, stars = "ABORT", "⚠️"
                reasons.append(f"\n🛑 <b>Decision:</b> ABORT. Insufficient on-chain confluence threshold to support technicals.")
                
            reasons.append(f"📊 <b>Confluence Framework Score: {confluence_score}/7</b>")

        reasoning = "\n".join(reasons)

    price_display = f"{payload.price:,.5f}" if is_forex else f"{payload.price:,.2f}"
    
    rich_message = (
        f"{'🟩' if decision == 'EXECUTE' else '🟥'} <b>DECISION: {decision} ({dir_label})</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💎 <b>Asset:</b> <code>${symbol}</code>\n"
        f"🏷️ <b>Sector:</b> <code>{sector}</code>\n"
        f"📊 <b>TF:</b> <code>{payload.timeframe}m</code> | <b>Price:</b> <code>${price_display}</code>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"{'🌍 <b>MACRO TELEMETRY</b>' if is_forex else '🛡️ <b>ON-CHAIN INTELLIGENCE</b>'}\n"
        f"• Status: <code>{metric_display}</code>\n• Conviction: {stars}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📝 <b>Analyst Brief:</b>\n{reasoning}\n"
        f"📈 <i>Confluence Engine V5.0</i>"
    )

    background_tasks.add_task(send_telegram_notification, rich_message)
    return {"status": "success", "decision": decision}