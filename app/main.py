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
    "USD": ["fed", "fomc", "powell", "dollar", "cpi", "nfp", "nonfarm", "treasury", "warsh"],
    "EUR": ["ecb", "lagarde", "eurozone", "euro", "inflation euro"],
    "GBP": ["boe", "bailey", "sterling", "pound", "uk economy"],
    "CHF": ["snb", "franc", "swiss", "kordan"],
    "JPY": ["boj", "yen", "ueda", "tokyo", "intervene"],
    "AUD": ["rba", "aussie", "australian"],
    "CAD": ["boc", "loonie", "canadian"],
    "NZD": ["rbnz", "kiwi", "zealand"]
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

async def check_forex_news_risk(symbol: str, base_ccy: str, quote_ccy: str, direction: str) -> dict:
    api_key = os.getenv("ALPHA_VANTAGE_KEY")
    av_ticker = f"FOREX:{base_ccy}{quote_ccy}"
    url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={av_ticker}&sort=LATEST&limit=15&apikey={api_key}"
    target_keys = CURRENCY_KEYWORDS.get(base_ccy, []) + CURRENCY_KEYWORDS.get(quote_ccy, [])

    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            res = await client.get(url)
            if res.status_code == 200:
                feed = res.json().get("feed", [])
                relevant_articles = []
                pattern = re.compile(r'\b(' + '|'.join(re.escape(tk) for tk in target_keys) + r')\b')
                for a in feed:
                    if pattern.search(f"{a.get('title', '')} {a.get('summary', '')}".lower()):
                        relevant_articles.append(a)

                if not relevant_articles:
                    return {"risk_score": 0.0, "sentiment": "NEUTRAL", "headline": "No active structural headlines on record.", "brief": "• Order-Flow: Volatility nominal.\n• Risk: Exposure baseline clear for technical execution."}
                
                top_article = relevant_articles[0]
                headline = top_article.get("title", "").split("...")[0].strip()
                sentiment_label = top_article.get("overall_sentiment_label", "NEUTRAL")

                usd_is_quote = (quote_ccy == "USD")
                if "BULLISH" in sentiment_label:
                    impact = f"Stronger US Dollar sentiment puts structural downward pressure on {base_ccy}/USD." if usd_is_quote else f"Bullish USD velocity driving expansion on USD/{quote_ccy} pair structures."
                elif "BEARISH" in sentiment_label:
                    impact = f"Weakening US Dollar parameters support structural local breakout extensions for {base_ccy}/USD." if usd_is_quote else f"Bearish Dollar liquidity metrics capping global upside extensions against {quote_ccy} environments."
                else:
                    impact = "USD liquidity structures printing completely stable inside tracking bounds."

                return {"risk_score": 0.0, "sentiment": sentiment_label, "headline": headline, "brief": f"• Macro Context: Financial streams print as {sentiment_label}.\n• Dynamic Impact: {impact}"}
        except: pass
    return {"risk_score": 0.0, "sentiment": "NEUTRAL", "headline": "Macro Pipeline Timeout", "brief": "• System Status: Running purely on technical chart parameters."}

@app.post("/webhook/tradingview")
@app.post("/webhook/tradingview/")
async def tradingview_webhook(payload: TradingViewPayload, background_tasks: BackgroundTasks):
    if payload.secret_token != os.getenv("TRADINGVIEW_SECRET", "hype_retest_2026"): raise HTTPException(status_code=401)

    raw_ticker = payload.ticker.upper().replace("/", "").replace("-", "").replace(" ", "").replace(".P", "")
    is_forex = len(raw_ticker) == 6 and raw_ticker[:3] in CURRENCY_KEYWORDS and raw_ticker[3:] in CURRENCY_KEYWORDS
    
    dir_label = "LONG" if payload.direction.upper() == "BUY" else "SHORT"
    decision, stars, reasoning, metric_display = "EXECUTE", "⭐⭐⭐", "", "Processing Data Matrix..."

    if is_forex:
        base_ccy, quote_ccy = raw_ticker[:3], raw_ticker[3:]
        symbol = f"{base_ccy}_{quote_ccy}"
        sector = f"Global FX | {base_ccy}-{quote_ccy} Cross"
        
        av_intel = await check_forex_news_risk(symbol, base_ccy, quote_ccy, payload.direction.upper())
        metric_display = f"AV: {av_intel['sentiment']}"
        reasoning = f"{av_intel['brief']}\n📰 <b>Latest:</b> {av_intel['headline']}"

    else:
        lookup_key = raw_ticker.split(":")[-1]
        for stable in ["USDT", "USDC", "USD"]:
            if lookup_key.endswith(stable) and lookup_key != stable:
                lookup_key = lookup_key[:-len(stable)]
                break
        
        symbol = CRYPTO_CLEAN_MAP.get(lookup_key, lookup_key)
        token_info = TOKEN_MAP.get(symbol)

        # 🛑 GHOST LAYER: Drops untracked webhooks instantly
        if not token_info:
            print(f"🛑 GHOST LAYER: {symbol} bypassed. Tracking matrix clean.")
            return {"status": "ignored", "reason": "Asset not configured."}

        sector = token_info.get("sector")
        pool_liquidity = await fetch_dex_liquidity_usd(chain=token_info.get("chain"), address=token_info.get("address"))
        
        metrics = await fetch_full_intelligence(symbol=symbol, address=token_info.get("address"), chain=token_info.get("chain"))
        if not metrics:
            metrics = {"net_flow_24h": 0, "cex_netflow": 0, "perp_bias": "NEUTRAL"}

        # Extract values for the Confluence Matrix
        smart_money_flow = metrics.get("net_flow_24h", 0)
        cex_24h_netflow = metrics.get("cex_netflow", 0)
        perp_leaderboard_bias = metrics.get("perp_bias", "NEUTRAL")
        direction = payload.direction.upper()

        if abs(smart_money_flow) >= 1_000_000: metric_display = f"${smart_money_flow/1e6:+.2f}M Flow"
        else: metric_display = f"${smart_money_flow/1e3:+.1f}K Flow"

        # 🛡️ THE DETERMINISTIC SCORING MATRIX
        confluence_score = 0
        reasons = []

        # Stream 1: Smart Money (Primary)
        if direction == "BUY" and smart_money_flow > 500_000:
            confluence_score += 3
            reasons.append("• <b>Primary Stream:</b> Smart Money Accumulation Mapped (+3)")
        elif direction == "SHORT" and smart_money_flow < -500_000:
            confluence_score += 3
            reasons.append("• <b>Primary Stream:</b> Smart Money Heavy Distribution Mapped (+3)")
        else:
            reasons.append("• <b>Primary Stream:</b> Smart Money Flow Flat/Neutral (+0)")

        # Stream 2: Exchange Supply Tracking (Secondary)
        if direction == "BUY" and cex_24h_netflow < -100_000:
            confluence_score += 2
            reasons.append("• <b>Secondary Stream:</b> Exchange Supply Shock / Outflows Verified (+2)")
        elif direction == "SHORT" and cex_24h_netflow > 100_000:
            confluence_score += 2
            reasons.append("• <b>Secondary Stream:</b> Exchange Inflows / Increase in Sell Pressures (+2)")
        else:
            reasons.append("• <b>Secondary Stream:</b> Exchange Supply Balance Stable (+0)")

        # Stream 3: Derivatives Leaderboard Tracking (Tertiary)
        if direction == "BUY" and perp_leaderboard_bias == "LONG":
            confluence_score += 2
            reasons.append("• <b>Tertiary Stream:</b> High-PnL Perp Traders Positioned LONG (+2)")
        elif direction == "SHORT" and perp_leaderboard_bias == "SHORT":
            confluence_score += 2
            reasons.append("• <b>Tertiary Stream:</b> High-PnL Perp Traders Positioned SHORT (+2)")
        else:
            reasons.append("• <b>Tertiary Stream:</b> Derivatives Bias Neutral (+0)")

        # Final Execution Hard Verification Boundaries
        if pool_liquidity < 250000.0:
            decision, stars = "ABORT", "⚠️"
            reasons.append(f"🛑 <b>CRITICAL RISK:</b> Liquidity depth sub-optimal (${pool_liquidity/1e3:,.0f}k). Execution blocked.")
        else:
            # Requires minimum 3 points across the cumulative streams to validate execution
            if confluence_score >= 3:
                decision, stars = "EXECUTE", "⭐⭐⭐⭐⭐"
            else:
                decision, stars = "ABORT", "⚠️"
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